


def analyse_refference_image():
    # return "Analyze the reference image for design elements focused solely on text-based content. This includes the background, text layout, font styles, font sizes, font colors, color palette, and overall visual structure. Do not include any analysis of icons, logos, website links, or graphical elements. Highlight how the text is placed and styled to convey its message, the intended audience, and any visual hierarchy used to prioritize information."
    return """
Examine this image as a professional graphic designer and provide clear, technical steps for text-only recreation.

Do NOT include:

Do not include any literal text from the image.

Instead, replace all visible text content with clearly named variables (e.g., {HEADLINE_LINE_1}, {SUBTEXT}, {HIGHLIGHT_WORD}).
Any references to or analysis of icons, logos, images, or URLs

Examples or usage scenarios

Your response should be limited to the following 5 structured sections, with only step-based instructions per section:

STEP 1: VISUAL INVENTORY
List only text-related visual elements:

Background appearance and its effect on text

Text content, font types, weights, and sizes

Color usage (name colors only: e.g., “white”, “dark blue”, “coral”)

Text effects (e.g., shadows, strokes, gradients)

Text alignment, grouping, and spacing layout

STEP 2: TECHNICAL MEASUREMENTS
Estimate and describe:

Text size ratios between elements (e.g., headline vs subtext)

Margin and padding as rough percentages of layout

Distribution of colors in the overall layout

Visual alignment and positioning balance

STEP 3: DESIGN PRINCIPLES ANALYSIS
Describe how the design works visually:

How contrast is created with text alone

How visual hierarchy is established using text styling

How visual consistency is maintained

How the layout guides the eye flow

STEP 4: TEXT-BASED RECREATION BLUEPRINT
Provide step-by-step instructions to rebuild the design with only text:

Set up the background and layout container

Place and style headline and supporting text

Apply sizing and spacing rules

Finalize layout using only text and positioning

STEP 5: VARIATION SYSTEM
Define how to turn this into a reusable template:

Support dynamic substitution of headline and description text

Ensure layout adjusts for varying text lengths

Maintain spacing, styling, and readability regardless of content.
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