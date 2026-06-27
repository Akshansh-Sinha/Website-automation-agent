from google import genai
from google.genai import types
import base64

def _build_user_message(screenshot_b64, prev_tool_name=None, prev_tool_result=None):
    parts = []
    if prev_tool_name and prev_tool_result is not None:
        parts.append(
            types.Part.from_function_response(
                name=prev_tool_name,
                response=prev_tool_result
            )
        )
    parts.append(types.Part.from_text(text="Here is the current state of the browser. What do you do next?"))
    parts.append(
        types.Part.from_bytes(
            data=base64.b64decode(screenshot_b64),
            mime_type="image/png"
        )
    )
    return types.Content(role="user", parts=parts)
