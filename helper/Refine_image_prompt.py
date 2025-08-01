import os
import json
from typing import Dict, Optional
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from helper.post_setting_helper import get_settings

load_dotenv()


# ---------- Structured Output Schema ----------
class FilledPrompt(BaseModel):
    composed_prompt: str = Field(description="Final text-to-image layout description with no placeholders.")
    negative_prompt: str = Field(description="Bans on icons, images, people, etc.")
    aspect_ratio: Optional[str] = Field(default=None, description="Aspect ratio like '1:1'.")
    variables_mapping: Dict[str, str] = Field(default_factory=dict, description="Resolved placeholders.")

    @classmethod
    def openai_schema(cls):
        return {
            "name": "generate_filled_prompt",
            "description": "Create a resolved text-to-image prompt based on layout blueprint and title/description.",
            "parameters": cls.schema()
        }



# ---------- Prompt Template ----------
# SYSTEM_INSTRUCTIONS = """\
# You are a layout-aware prompt composer for text-to-image generation, focused on typographic posters that may include decorative or iconographic elements.

# You will receive:
# - A JSON blueprint describing the visual layout: fonts, colors in hexa, alignment, spacing, positioning, aspect ratio, and visual restrictions.
# - A TITLE and DESCRIPTION string to insert into the layout.

# Your output must:
# 1. Write a **visual description** of how the final poster looks, in fluent English — not as code, not as raw lines of text.
# 2. Accurately describe the layout of all text blocks: their order, font style (e.g. bold sans-serif), casing (e.g. uppercase), alignment (e.g. centered), spacing, and width.
# 3. Match the font weight, line height, alignment, and positioning exactly as described in the JSON.
# 4. If a text block's `color` field contains **multiple values** (e.g. `"white | coral"`), you must describe the **visual effect** of that — such as alternating colors by word, line, or segment — matching the structure of the input title or description.
# 5. Replace all variables like `{{TITLE_LINE_1}}` or `{{SUBTEXT}}` with the actual title or description provided.
# 6. If icons or shapes are included in the layout, describe them briefly: style, color, and position. If banned in the JSON, exclude them entirely.
# 7. DO NOT output raw text lines. Describe the layout as it would visually appear on a poster.
# 8. Follow character limits such as `max_chars_per_line` to determine line breaks.
# 9. Avoid any unresolved {{...}} placeholders.

# Your goal is to generate a prompt that visually matches the design blueprint exactly — respecting every layout rule from the JSON — but describing it in natural, fluent English for a text-to-image model.
# """


# HUMAN_TEMPLATE = """\
# [BLUEPRINT JSON]
# {blueprint_json}

# [TITLE]
# {title}

# [DESCRIPTION]
# {description}

# You must generate:
# - composed_prompt: A fluent natural-language description of how the final poster looks. 
#   Include:
#   • Background color in hex and any patterns or textures (e.g. subtle waves, gradients, solid fills).  
#   • The layout and appearance of all text blocks — font style, casing, weight, alignment, color, spacing, position, and width.  
#   • If a text block lists multiple colors (e.g. "white | coral"), describe how these colors are applied (e.g. alternating by word or line).  
 
# - negative_prompt: A strong ban list for text-to-image generation (no photos, people, icons, gradients, scenery, busy textures).
# - aspect_ratio: From the blueprint.
# - variables_mapping: Dictionary mapping each placeholder to the actual line used.
# """
# ---------- Prompt Template ----------
# ...existing code...
# ...existing code...

SYSTEM_INSTRUCTIONS = """\
You are a layout-aware prompt composer for text-to-image generation, focused on typographic posters that may include decorative or iconographic elements.

You will receive:
- A JSON blueprint describing the visual layout: fonts, colors in rgba format, alignment, spacing, positioning, aspect ratio, and visual restrictions.
- A TITLE and DESCRIPTION string to insert into the layout.

Your output must:
1. Write a **visual description** of how the final poster looks, in fluent English — not as code, not as raw lines of text.
2. Accurately describe the layout of all text blocks: their order, font style (e.g. bold sans-serif), casing (e.g. uppercase), alignment (e.g. centered), spacing, and width.
3. Match the font weight, line height, alignment, and positioning exactly as described in the JSON.
4. If a text block's `color` field contains **multiple values** (e.g. `"white | coral"`), you must describe the **visual effect** of that — such as alternating colors by word, line, or segment — matching the structure of the input title or description.
5. **Colors**: For every color mentioned (background, text, etc.), you MUST provide **RGBA** (e.g. `rgba(255, 255, 255, 1)`) formats. Do NOT use color names alone. If the input uses a color name, convert it to both hex and RGBA and include both in your description.
6. If there is **more than one background color** (e.g., a gradient, split, or pattern), list **all background colors** in RGBA, and clearly describe **how each color is used** (such as gradient direction, split areas, or pattern details).
7. Replace all variables like `{{TITLE_LINE_1}}` or `{{SUBTEXT}}` with the actual title or description provided.
8. If icons or shapes are included in the layout, describe them briefly: style, color, and position. If banned in the JSON, exclude them entirely.
9. DO NOT output raw text lines. Describe the layout as it would visually appear on a poster.
10. Follow character limits such as `max_chars_per_line` to determine line breaks.
11. Avoid any unresolved {{...}} placeholders.

Your goal is to generate a prompt that visually matches the design blueprint exactly — respecting every layout rule from the JSON — but describing it in natural, fluent English for a text-to-image model.
"""

HUMAN_TEMPLATE = """\
[BLUEPRINT JSON]
{blueprint_json}

[TITLE]
{title}

[DESCRIPTION]
{description}

You must generate:
- composed_prompt: A fluent natural-language description of how the final poster looks. 
  Include:
  • Background color in **RGBA** (e.g., `rgba(255, 255, 255, 1)`), along with any patterns or textures (e.g., subtle waves, gradients, solid fills).  
  • If there is **more than one background color**, list all background colors in RGBA, and describe **how each color is used** (e.g., gradient, split, pattern).
  • The layout and appearance of all text blocks — font style, casing, weight, alignment, color (RGBA), spacing, position, and width.  
  • If a text block lists multiple colors (e.g. "white | coral"), describe how these colors are applied (e.g. alternating by word or line in RGBA).  
 
- negative_prompt: A strong ban list for text-to-image generation (no photos, people, icons, gradients, scenery, busy textures).
- aspect_ratio: From the blueprint.
- variables_mapping: Dictionary mapping each placeholder to the actual line used.
"""


# ---------- LangChain Composition Function ----------
async def compose_prompt_via_langchain(
    reference_layout_json: dict,
    title: str,
    description: str,
    model: str = "gpt-4o-mini",

) -> FilledPrompt:
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_INSTRUCTIONS),
        ("human", HUMAN_TEMPLATE),
    ])
    
    try:
        settings = await get_settings()
        llm = ChatOpenAI(
            model=model,
            temperature=0.1,
            openai_api_key=settings["openai_api_key"],
        ).with_structured_output(FilledPrompt, method="function_calling")
    except Exception:
        print("error in here")
        settings = await get_settings()
        llm = ChatOpenAI(
            model=model,
            temperature=0.1,
            openai_api_key=settings["openai_api_key"],
        ).with_structured_output(FilledPrompt, method="function_calling")

    chain = prompt | llm

    result: FilledPrompt = chain.invoke({
        "blueprint_json": json.dumps(reference_layout_json, ensure_ascii=False),
        "title": title.strip(),
        "description": description.strip(),
    })

    if not result.aspect_ratio and reference_layout_json.get("aspect_ratio"):
        result.aspect_ratio = reference_layout_json["aspect_ratio"]
    print(f"Resutl of composer prompt = {result}")
    return result


# # ---------- Run with Your Example ----------
# if __name__ == "__main__":
#     blueprint = {
#         "background": {
#             "color": "dark blue",
#             "pattern": "subtle waves"
#         },
#         "aspect_ratio": "1:1",
#         "blocks": [
#             {
#                 "id": "HEADLINE",
#                 "role": "headline",
#                 "variables": [
#                     "{TITLE_LINE_1}", "{TITLE_LINE_2}", "{TITLE_LINE_3}", "{TITLE_LINE_4}"
#                 ],
#                 "font_family": "sans",
#                 "font_weight": 800,
#                 "case": "uppercase",
#                 "color": "white | coral",
#                 "align": "center",
#                 "anchor_xy_pct": [10, 20],
#                 "width_pct": 80,
#                 "line_height_pct": 120,
#                 "max_chars_per_line": 15,
#                 "effects": ["none"]
#             },
#             {
#                 "id": "SUBTEXT",
#                 "role": "description",
#                 "variables": ["{URL}"],
#                 "font_family": "sans",
#                 "font_weight": 400,
#                 "case": "normal",
#                 "color": "white",
#                 "align": "center",
#                 "anchor_xy_pct": [10, 85],
#                 "width_pct": 80,
#                 "line_height_pct": 120,
#                 "max_chars_per_line": 40,
#                 "effects": ["none"]
#             }
#         ],
#         "effects": {
#             "text_shadow": "none",
#             "text_stroke": "none"
#         },
#         "negative_elements": ["icons", "logos", "images", "URLs"]
#     }

#     title_text = "Invest in Health Services"
#     description_text = "Make a difference with your donation."

#     filled = compose_prompt_via_langchain(
#         reference_layout_json=blueprint,
#         title=title_text,
#         description=description_text,
#         model="gpt-4o-mini"
#     )

#     print("=== composed_prompt ===")
#     print(filled.composed_prompt)
#     print("\n=== negative_prompt ===")
#     print(filled.negative_prompt)
#     print("\n=== aspect_ratio ===")
#     print(filled.aspect_ratio)
#     print("\n=== variables_mapping ===")
#     print(json.dumps(filled.variables_mapping, indent=2))
