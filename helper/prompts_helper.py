


def analyse_refference_image():
    # return "Analyze the reference image for design elements focused solely on text-based content. This includes the background, text layout, font styles, font sizes, font colors, color palette, and overall visual structure. Do not include any analysis of icons, logos, website links, or graphical elements. Highlight how the text is placed and styled to convey its message, the intended audience, and any visual hierarchy used to prioritize information."
    return """
You are an expert layout designer and visual analyst.

You will examine the uploaded image and extract a JSON blueprint describing the layout of **text elements only** (no icons, photos, or logos).

Return ONLY structured JSON with the following format:

{
  "background": {
    "color": "white | dark blue | gradient | etc.",
    "pattern": "none | subtle waves | diagonal lines | etc."
  },
  "aspect_ratio": "4:5 | 1:1 | 16:9 | etc.",
  "blocks": [
    {
      "id": "HEADLINE",
      "role": "headline | subheading | description",
      "variables": ["{TITLE_LINE_1}", "{TITLE_LINE_2}"],
      "font_family": "sans | serif",
      "font_weight": 400 | 600 | 800,
      "case": "uppercase | titlecase | normal",
      "color": "white | black | coral | etc.",
      "align": "left | center | right",
      "anchor_xy_pct": [X%, Y%],       // top-left anchor of block
      "width_pct": %width_of_text_block,
      "line_height_pct": %line_height_relative_to_font,
      "max_chars_per_line": approximate_max,
      "effects": ["shadow", "stroke", "outline", "none"]
    },
    {
      "id": "SUBTEXT",
      ...
    }
  ],
  "effects": {
    "text_shadow": "none | soft | strong",
    "text_stroke": "none | thin | bold"
  },
  "negative_elements": ["icons", "logos", "images", "URLs"]
}

Additional rules:

- Only describe text-based layout and design.
- Do NOT return any literal text or example words from the image.
- Variable placeholders like {TITLE_LINE_1} must represent where dynamic user text will go.
- Approximate all values in percent, not pixels.
- Avoid any references to brand names, people, products, or photos.

Return the JSON directly, with no explanation or prose.
"""
    




#            { "text_only": """Analyse this image carefully and extract the elements in the design. We need to understand the design, how the background looks, how the text is there, what's the font size, colors used etc. Everything.

# Provide a comprehensive design analysis including:

# 1. **Color Scheme**: All colors used (primary, secondary, accent colors)
# 2. **Typography**: Font styles, sizes, weights, spacing between text elements
# 3. **Background**: Type, texture, effects, gradients, patterns
# 4. **Layout Structure**: Composition, alignment, balance, visual hierarchy
# 5. **Spacing**: Padding, margins, gaps between elements
# 6. **Visual Elements**: Any graphics, icons, shapes, borders, shadows
# 7. **Design Style**: Overall aesthetic, mood, visual approach

# Return ONLY valid JSON with this structure:
# {
#     "color_scheme": {
#         "primary_colors": ["color1", "color2"],
#         "secondary_colors": ["color1", "color2"],
#         "accent_colors": ["color1", "color2"],
#         "background_color": "color"
#     },
#     "typography": {
#         "font_styles": ["style1", "style2"],
#         "font_sizes": ["size1", "size2"],
#         "font_weights": ["weight1", "weight2"],
#         "text_spacing": "description",
#         "text_alignment": "left/center/right"
#     },
#     "background": {
#         "type": "solid/gradient/texture/pattern",
#         "effects": "description",
#         "texture_details": "description"
#     },
#     "layout": {
#         "composition": "description",
#         "alignment": "description",
#         "balance": "description",
#         "visual_hierarchy": "description"
#     },
#     "spacing": {
#         "padding": "description",
#         "margins": "description",
#         "element_gaps": "description"
#     },
#     "visual_elements": {
#         "graphics": ["element1", "element2"],
#         "shapes": ["shape1", "shape2"],
#         "borders": "description",
#         "shadows": "description"
#     },
#     "design_style": {
#         "aesthetic": "description",
#         "mood": "description",
#         "overall_approach": "description"
#     }
# }""",
            
#             "image_only": """Analyze this image and provide a concise layout analysis focusing ONLY on:
# 1. **Color Scheme**: Main colors used (max 3-4 colors)
# 2. **Spacing**: Padding and margins around elements
# 3. **Background**: Type and any effects
# 4. **Layout Structure**: Basic composition and balance

# DO NOT include any visual element analysis.
# Keep the response under 320 characters total.

# Return ONLY valid JSON with this structure:
# {
#     "color_scheme": {
#         "main_colors": ["color1", "color2", "color3"],
#         "accent_colors": ["color1", "color2"]
#     },
#     "spacing": {
#         "padding": "brief description",
#         "margins": "brief description"
#     },
#     "background": {
#         "type": "brief description",
#         "effects": "brief description"
#     },
#     "layout": {
#         "composition": "brief description",
#         "balance": "brief description"
#     }
# }""",
            
#             "both": """Analyze this image and provide a concise layout analysis focusing ONLY on:
# 1. **Color Scheme**: Main colors used (max 3-4 colors)
# 2. **Spacing**: Padding and margins around elements
# 3. **Background**: Type and any effects
# 4. **Layout Structure**: Basic composition and balance

# DO NOT include any text or visual element content analysis.
# Keep the response under 320 characters total.

# Return ONLY valid JSON with this structure:
# {
#     "color_scheme": {
#         "main_colors": ["color1", "color2", "color3"],
#         "accent_colors": ["color1", "color2"]
#     },
#     "spacing": {
#         "padding": "brief description",
#         "margins": "brief description"
#     },
#     "background": {
#         "type": "brief description",
#         "effects": "brief description"
#     },
#     "layout": {
#         "composition": "brief description",
#         "balance": "brief description"
#     }
# }"""
# }