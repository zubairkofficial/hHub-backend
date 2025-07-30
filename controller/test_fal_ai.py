from fastapi import APIRouter, HTTPException, Path, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from helper.business_post_helper import BusinessPostHelper
from helper.fall_ai import fall_ai_image_generator
from openai import OpenAI
from langchain_openai import ChatOpenAI
import uuid
import os
import requests
import fal_client


router = APIRouter()

@router.post("/fal/ai")
async def callApi():
    prompt = """**Design Brief / Prompt for Text-Based Recreation**\n\n---\n\n### STEP 1: VISUAL INVENTORY\n\n- **Background:**  \n  - Solid medium-dark blue base with a subtle abstract wavy pattern in a slightly darker blue tone.  \n  - Pattern is low contrast, ensuring text readability remains high.\n\n- **Text Content:**  \n  - Headline: \"ELEVATE YOUR SMILE, TO THE MAXIMUM!\"  \n  - URL/subtext: \"www.seaglassorthodontics.com\"\n\n- **Font Types & Weights:**  \n  - Headline: Bold, sans-serif, uppercase.  \n  - URL/subtext: Regular weight, sans-serif, lowercase.\n\n- **Font Sizes:**  \n  - Headline: Large, dominant size.  \n  - URL/subtext: Much smaller, secondary size.\n\n- **Color Usage:**  \n  - Headline text: Mostly white.  \n  - Emphasized words (\"SMILE,\" and \"MAXIMUM!\"): coral/orange-pink tone.  \n  - URL/subtext: White, smaller and less prominent.\n\n- **Text Effects:**  \n  - No visible shadows, strokes, or gradients on text.  \n  - Clean, flat color application.\n\n- **Structural Layout:**  \n  - Center aligned text block vertically and horizontally.  \n  - Headline broken into multiple lines for emphasis and rhythm:  \n    - Line 1: \"ELEVATE\"  \n    - Line 2: \"YOUR SMILE,\"  \n    - Line 3: \"TO THE\"  \n    - Line 4: \"MAXIMUM!\"  \n  - URL placed below headline block with generous spacing.\n\n---\n\n### STEP 2: TECHNICAL MEASUREMENTS\n\n- **Text Size Ratios:**  \n  - Headline font size approx. 4-5 times larger than URL text.  \n  - Emphasized words in headline slightly larger or same size but differentiated by color.\n\n- **Margin and Padding:**  \n  - Outer padding around text block approx. 15-20% of total width on each side.  \n  - Vertical spacing between headline lines roughly equal, about 10-15% of headline font size.  \n  - Space between headline block and URL approx. 30-40% of headline font size.\n\n- **Color Distribution:**  \n  - Background blue: ~70% of visual area.  \n  - White text: ~20%.  \n  - Coral/orange-pink accent text: ~10%.\n\n- **Balance and Alignment:**  \n  - Perfectly centered alignment creates symmetrical balance.  \n  - Text block is compact but with breathing room around edges.\n\n---\n\n### STEP 3: DESIGN PRINCIPLES ANALYSIS\n\n- **Contrast:**  \n  - Achieved through strong color contrast: white and coral text on dark blue background.  \n  - Coral accent words draw attention without additional graphic elements.\n\n- **Visual Hierarchy:**  \n  - Large, bold uppercase headline dominates.  \n  - Color accentuation on key words (\"SMILE,\" \"MAXIMUM!\") creates focal points.  \n  - Smaller URL text clearly secondary.\n\n- **Consistency:**  \n  - Uniform font family and uppercase style in headline.  \n  - Consistent spacing and alignment throughout.\n\n- **Eye Flow:**  \n  - Eye naturally moves top to bottom through headline lines.  \n  - Color changes create pauses and emphasis.  \n  - Final stop at URL below headline.\n\n---\n\n### STEP 4: TEXT-BASED RECREATION BLUEPRINT\n\n1. **Background & Base Layout:**  \n   - Set background color to medium-dark blue.  \n   - Overlay subtle wavy pattern in a slightly darker blue (optional for text-only).  \n   - Center all text horizontally and vertically within the container.\n\n2. **Headline Placement & Styling:**  \n   - Use a bold, uppercase sans-serif font.  \n   - Break headline into four lines:  \n     - Line 1: \"ELEVATE\" (white)  \n     - Line 2: \"YOUR SMILE,\" (white for \"YOUR\", coral for \"SMILE,\")  \n     - Line 3: \"TO THE\" (white)  \n     - Line 4: \"MAXIMUM!\" (coral)  \n   - Font size large enough to dominate (approx. 4-5x URL size).  \n   - Line spacing about 10-15% of font size.\n\n3. **URL/Subtext Placement & Styling:**  \n   - Place below headline block with vertical margin approx. 30-40% of headline font size.  \n   - Use smaller, regular weight sans-serif font in white.  \n   - Lowercase text.\n\n4. **Spacing & Sizing:**  \n   - Apply horizontal padding of 15-20% container width.  \n   - Maintain consistent vertical spacing between lines and between headline and URL.\n\n---\n\n### STEP 5: VARIATION SYSTEM (Reusable Template)\n\n**Template Variables:**  \n- `{TITLE_LINE_1}`  \n- `{TITLE_LINE_2_PART1}`  \n- `{TITLE_LINE_2_PART2}` (accent color)  \n- `{TITLE_LINE_3}`  \n- `{TITLE_LINE_4}` (accent color)  \n- `{URL}`\n\n**Template Rules:**  \n- Background: medium-dark blue with optional subtle pattern.  \n- Headline: bold uppercase sans-serif, white color except `{TITLE_LINE_2_PART2}` and `{TITLE_LINE_4}` in coral.  \n- URL: smaller, regular weight, lowercase, white.  \n- Center all text horizontally and vertically.  \n- Maintain spacing ratios:  \n  - Headline font size approx. 4-5x URL font size.  \n  - Vertical spacing between headline lines ~10-15% of headline font size.  \n  - Space between headline block and URL ~30-40% of headline font size.  \n  - Horizontal padding 15-20% container width.\n\n**Adaptability:**  \n- If `{TITLE_LINE_2_PART2}` or `{TITLE_LINE_4}` are longer or shorter, keep font size consistent; allow line breaks if needed.  \n- Adjust vertical spacing slightly if headline grows to maintain balance.  \n- URL text length can vary; keep font size fixed for consistency.\n\n---\n\n**Example Usage:**  \n- Replace variables with new text while preserving color and style rules.  \n- Ensure headline remains center aligned and visually balanced.  \n- Keep coral accent on key words for emphasis.\n\n---\n\nThis brief enables precise text-only recreation of the original design with flexibility for dynamic content changes while maintaining strong visual impact and readability."""
    style = ""
    response = fall_ai_image_generator(prompt, style)
    return response

@router.get('/openai/image')
async def callOpenAIImage():
    prompt = """
        Design Style
✅ Revised Text Content:
vbnet
Copy
Edit
50% OFF
on new
Braces Promotion
🔤 Typography Adjustments:
Line 1: "50% OFF"
Font Style: Bold, All Caps (same as "MAXIMUM!")

Color: Coral (#F16F5C) — this is the high-impact visual anchor

Font Size: Largest (~34–38px) — make this pop the most

Purpose: Immediate attention-grabber — headline of the promo

Line 2: "on new"
Font Style: Bold, All Caps

Color: White

Font Size: Medium (~28px)

Purpose: Supporting content — lower emphasis

Line 3: "Braces Promotion"
Font Style: Bold, All Caps

Color: White, or alternate with Coral for just "Braces"

Font Size: Slightly larger (~30–32px)

Purpose: Clarifies what the promotion is about — keep it legible and prominent

🎨 Updated Color Usage
Coral (#F16F5C): Use for "50% OFF" (and optionally for "Braces")

White: Use for "on new" and "Promotion"

Maintain contrast against navy blue background.

📐 Text Layout & Alignment
Still center-aligned (like original)

Use line breaks smartly:

vbnet
Copy
Edit
50% OFF
on new
Braces Promotion
Optionally, make "Braces" and "Promotion" two lines if vertical spacing allows.

🌐 Footer (Website URL)
No changes — keep:

Copy
Edit
www.seaglassorthodontics.com
Small font, white, centered at bottom
    """
    
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.images.generate(
            model="dall-e-2",
            prompt=prompt,
            size="1024x1024",
            # quality="standard",
            n=1
        )
        return {"image_url": response.data[0].url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating image: {str(e)}")