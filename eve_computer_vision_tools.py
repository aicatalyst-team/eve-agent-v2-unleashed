"""
Eve Computer Vision Tools
=========================
Tools for taking screenshots, analyzing screen content, and interacting with GUI elements.
These tools integrate OpenClaw's computer-use capabilities into Eve's agentic loop.
"""

import base64
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np
import pyautogui
from PIL import Image
from eve.tools.base import Tool

logger = logging.getLogger(__name__)

# Configure pyautogui settings
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.5


class EveTakeScreenshotTool(Tool):
    """Take a screenshot of the current screen or a specific region."""

    name = "eve_take_screenshot"
    description = (
        "Take a screenshot of the current screen or a specific region. "
        "Returns a base64 encoded image that can be analyzed by vision models. "
        "Useful for understanding the current state of the GUI or monitoring application behavior."
    )

    def get_parameters(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "region": {
                    "type": "object",
                    "properties": {
                        "left": {"type": "integer", "description": "Left coordinate of region"},
                        "top": {"type": "integer", "description": "Top coordinate of region"},
                        "width": {"type": "integer", "description": "Width of region"},
                        "height": {"type": "integer", "description": "Height of region"},
                    },
                    "description": "Region of screen to capture (optional, captures full screen if not provided)",
                },
                "save_path": {
                    "type": "string",
                    "description": "Path to save screenshot (optional)",
                },
            },
        }

    async def __call__(self, region: Optional[Dict] = None, save_path: Optional[str] = None) -> Dict:
        try:
            # Take screenshot
            if region:
                screenshot = pyautogui.screenshot(region=(region["left"], region["top"], region["width"], region["height"]))
            else:
                screenshot = pyautogui.screenshot()

            # Save to file if requested
            if save_path:
                save_path = Path(save_path)
                save_path.parent.mkdir(parents=True, exist_ok=True)
                screenshot.save(save_path)

            # Convert to base64 for vision model analysis
            import io
            buffer = io.BytesIO()
            screenshot.save(buffer, format="PNG")
            img_str = base64.b64encode(buffer.getvalue()).decode()

            return {
                "success": True,
                "image_base64": img_str,
                "message": f"Screenshot taken successfully{' and saved to ' + str(save_path) if save_path else ''}",
            }
        except Exception as e:
            logger.error(f"Error taking screenshot: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to take screenshot",
            }


class EveAnalyzeScreenContentTool(Tool):
    """Analyze the content of the current screen using OCR and computer vision."""

    name = "eve_analyze_screen_content"
    description = (
        "Analyze the content of the current screen using OCR and computer vision techniques. "
        "Can identify text, UI elements, windows, and general screen layout. "
        "Useful for understanding what is currently displayed on screen."
    )

    def get_parameters(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "region": {
                    "type": "object",
                    "properties": {
                        "left": {"type": "integer", "description": "Left coordinate of region"},
                        "top": {"type": "integer", "description": "Top coordinate of region"},
                        "width": {"type": "integer", "description": "Width of region"},
                        "height": {"type": "integer", "description": "Height of region"},
                    },
                    "description": "Region of screen to analyze (optional, analyzes full screen if not provided)",
                },
                "analysis_type": {
                    "type": "string",
                    "enum": ["text", "ui_elements", "layout", "full"],
                    "description": "Type of analysis to perform (default: full)",
                },
            },
        }

    async def __call__(self, region: Optional[Dict] = None, analysis_type: str = "full") -> Dict:
        try:
            # Take screenshot
            if region:
                screenshot = pyautogui.screenshot(region=(region["left"], region["top"], region["width"], region["height"]))
            else:
                screenshot = pyautogui.screenshot()

            # Convert PIL image to OpenCV format
            open_cv_image = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

            results = {}

            # Perform OCR if requested
            if analysis_type in ["text", "full"]:
                try:
                    import pytesseract
                    # Extract text using OCR
                    text = pytesseract.image_to_string(screenshot)
                    results["text"] = text.strip()
                except ImportError:
                    results["text"] = "OCR not available (pytesseract not installed)"

            # Analyze UI elements if requested
            if analysis_type in ["ui_elements", "full"]:
                # Simple UI element detection using contour detection
                gray = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2GRAY)
                blurred = cv2.GaussianBlur(gray, (5, 5), 0)
                edged = cv2.Canny(blurred, 50, 150)
                
                contours, _ = cv2.findContours(edged.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                
                # Filter for likely UI elements (rectangular shapes)
                ui_elements = []
                for contour in contours:
                    # Approximate contour to polygon
                    epsilon = 0.02 * cv2.arcLength(contour, True)
                    approx = cv2.approxPolyDP(contour, epsilon, True)
                    
                    # Check if it's roughly rectangular and of reasonable size
                    if len(approx) == 4:
                        x, y, w, h = cv2.boundingRect(contour)
                        # Filter by size (avoid very small or very large elements)
                        if 20 < w < 1000 and 20 < h < 800:
                            ui_elements.append({
                                "type": "rectangle",
                                "coordinates": {"x": x, "y": y, "width": w, "height": h},
                                "area": w * h
                            })
                
                results["ui_elements"] = ui_elements

            # Analyze layout if requested
            if analysis_type in ["layout", "full"]:
                # Get basic layout information
                width, height = screenshot.size
                results["screen_dimensions"] = {"width": width, "height": height}
                
                # Detect dominant colors (simplified)
                # Resize image for faster processing
                small_img = screenshot.resize((50, 50))
                colors = small_img.getcolors(50 * 50)
                if colors:
                    # Get top 3 most common colors
                    colors.sort(reverse=True)
                    dominant_colors = [color[1] for color in colors[:3]]
                    results["dominant_colors"] = dominant_colors

            return {
                "success": True,
                "analysis": results,
                "message": f"Screen content analyzed successfully (type: {analysis_type})",
            }
        except Exception as e:
            logger.error(f"Error analyzing screen content: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to analyze screen content",
            }


class EveGuiInteractionTool(Tool):
    """Interact with GUI elements through mouse and keyboard actions."""

    name = "eve_gui_interaction"
    description = (
        "Interact with GUI elements through mouse and keyboard actions. "
        "Can move mouse, click, type text, and perform keyboard shortcuts. "
        "Useful for automating GUI interactions based on visual analysis."
    )

    def get_parameters(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["move_mouse", "click", "double_click", "right_click", "type_text", "key_press", "key_combination"],
                    "description": "Type of GUI interaction to perform",
                },
                "x": {
                    "type": "integer",
                    "description": "X coordinate for mouse actions",
                },
                "y": {
                    "type": "integer",
                    "description": "Y coordinate for mouse actions",
                },
                "text": {
                    "type": "string",
                    "description": "Text to type for type_text action",
                },
                "key": {
                    "type": "string",
                    "description": "Key to press for key_press action",
                },
                "keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Keys to press simultaneously for key_combination action",
                },
                "duration": {
                    "type": "number",
                    "description": "Duration of mouse movement in seconds (optional)",
                },
            },
            "required": ["action"],
        }

    async def __call__(self, action: str, x: Optional[int] = None, y: Optional[int] = None, 
                       text: Optional[str] = None, key: Optional[str] = None, keys: Optional[List[str]] = None,
                       duration: Optional[float] = None) -> Dict:
        try:
            if action == "move_mouse":
                if x is None or y is None:
                    return {"success": False, "error": "x and y coordinates required for move_mouse action"}
                pyautogui.moveTo(x, y, duration=duration or 0.5)
                return {"success": True, "message": f"Mouse moved to ({x}, {y})"}
            
            elif action == "click":
                if x is not None and y is not None:
                    pyautogui.click(x, y)
                else:
                    pyautogui.click()
                return {"success": True, "message": "Mouse clicked"}
            
            elif action == "double_click":
                if x is not None and y is not None:
                    pyautogui.doubleClick(x, y)
                else:
                    pyautogui.doubleClick()
                return {"success": True, "message": "Mouse double-clicked"}
            
            elif action == "right_click":
                if x is not None and y is not None:
                    pyautogui.rightClick(x, y)
                else:
                    pyautogui.rightClick()
                return {"success": True, "message": "Mouse right-clicked"}
            
            elif action == "type_text":
                if text is None:
                    return {"success": False, "error": "text parameter required for type_text action"}
                pyautogui.write(text)
                return {"success": True, "message": f"Typed text: {text}"}
            
            elif action == "key_press":
                if key is None:
                    return {"success": False, "error": "key parameter required for key_press action"}
                pyautogui.press(key)
                return {"success": True, "message": f"Pressed key: {key}"}
            
            elif action == "key_combination":
                if keys is None or len(keys) == 0:
                    return {"success": False, "error": "keys parameter required for key_combination action"}
                pyautogui.hotkey(*keys)
                return {"success": True, "message": f"Pressed key combination: {'+'.join(keys)}"}
            
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
                
        except Exception as e:
            logger.error(f"Error performing GUI interaction: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to perform GUI interaction: {action}",
            }


# Export tools
COMPUTER_VISION_TOOLS = [
    EveTakeScreenshotTool(),
    EveAnalyzeScreenContentTool(),
    EveGuiInteractionTool(),
]