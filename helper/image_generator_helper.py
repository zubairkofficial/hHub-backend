def get_focus_area_instruction(focus_area):
            """Generate focus area instruction based on selection"""
            if focus_area == "center":
                return "Center composition, balanced symmetry"
            elif focus_area == "left":
                return "Left-aligned focus and elements"
            elif focus_area == "right":
                return "Right-aligned focus and elements"
            elif focus_area == "random":
                return "Asymmetrical, dynamic placement"
            else:
                return "Balanced composition"

def get_background_instruction(background_type):
            """Generate background instruction based on selection"""
            if background_type == "plain":
                return "Clean solid background"
            elif background_type == "textured":
                return "Subtle textured background"
            elif background_type == "gradient":
                return "Smooth gradient background"
            else:
                return "Complementary background"

def get_mood_instruction(image_mood):
            """Generate mood instruction based on selection"""
            if image_mood == "cheerful":
                return "Upbeat, vibrant, energetic"
            elif image_mood == "calm":
                return "Peaceful, soft tones"
            elif image_mood == "mysterious":
                return "Intriguing, deeper tones"
            else:
                return "Balanced emotional tone"

def get_lighting_instruction(lighting_effects):
            """Generate lighting instruction based on selection"""
            if lighting_effects == "bright":
                return "Bright, well-lit"
            elif lighting_effects == "soft":
                return "Gentle, diffused lighting"
            elif lighting_effects == "dramatic":
                return "High-contrast, bold shadows"
            else:
                return "Natural balanced lighting"

def truncate_text(text, max_length=100):
            """Truncate text to specified length"""
            if not text:
                return ""
            return text[:max_length] + "..." if len(text) > max_length else text

def validate_and_trim_prompt(prompt, max_length=2500):
            """Check prompt length and trim if necessary"""
            if len(prompt) <= max_length:
                return prompt
            