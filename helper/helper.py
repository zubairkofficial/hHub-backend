import os
import uuid
import base64
from io import BytesIO
from PIL import Image

def get_image_path(folder_name: str, image_name: str) -> str:
    """
    Constructs and returns the full path to the image inside the given folder.
    Folder is assumed to be one level above this file.

    Args:
        folder_name (str): Name of the folder (e.g. 'reference_images')
        image_name (str): Name of the image file (e.g. 'cat.png')

    Returns:
        str: Full absolute path to the image file
    """
    folder_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', folder_name)
    return os.path.join(folder_path, image_name)


def image_to_base64(image_path: str) -> str:
    """
    Reads an image file and returns the base64-encoded string (OpenAI-compatible).
    OpenAI format: data:<mime-type>;base64,<base64-data>

    Args:
        image_path (str): Full path to the image file.

    Returns:
        str: Base64-encoded image string suitable for OpenAI
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    mime_type = "image/png"  # Modify as needed
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    return f"data:{mime_type};base64,{encoded_string}"

    
def save_base64_image_original(base64_image: str, save_dir: str,file_extension:str = "png") -> str:
    """
    This function takes a base64 encoded image, decodes it, saves it to the specified directory,
    and returns the image ID (UUID) along with the file extension. If no extension is provided,
    it defaults to 'png'.

    :param base64_image: Base64 encoded image string
    :param save_dir: The directory where the image should be saved
    :return: The image ID and extension
    """
    try:
        # Check if the directory exists, create if not
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        # Split the base64 string into header and data
        data = base64_image.split(",", 1)[-1] if "," in base64_image else base64_image

        # Generate a unique image ID (UUID) for the image
        image_id = str(uuid.uuid4())

        # Construct the file path
        filename = f"{image_id}.{file_extension}"
        filepath = os.path.join(save_dir, filename)

        # Decode base64 to image bytes
          # Attempt to decode base64 data
        try:
            img_bytes = base64.b64decode(data)
        except Exception as e:
            raise Exception(f"Base64 decoding failed: {e}")

        # Save the image bytes to the specified file
        with open(filepath, "wb") as f:
            f.write(img_bytes)
        print(f"save image name like this = {image_id}.{file_extension}")
        # Return the image ID (UUID) and extension
        return f"{image_id}.{file_extension}"

    except Exception as e:
        raise Exception(f"Error saving the base64 image: {e}")

def save_base64_image(base64_image: str, save_dir: str, reference_image_path: str, file_extension: str = "png") -> str:
    """
    Decodes a base64 image, resizes it to match the reference image's dimensions, saves it to the specified directory,
    and returns the image ID along with the file extension.

    :param base64_image: Base64 encoded image string
    :param save_dir: Directory where the image should be saved
    :param reference_image_path: Path to the reference image for dimension matching
    :param file_extension: Desired file extension (default is 'png')
    :return: Image ID and extension
    """
    try:
        original_image = save_base64_image_original(base64_image,save_dir)
        print(f"Original Image = {original_image}")
        # Check if the directory exists, create if not
        # if not os.path.exists(save_dir):
        #     os.makedirs(save_dir)

        # # Decode the base64 image
        # image_data = base64.b64decode(base64_image.split(",", 1)[-1])
        # image = Image.open(BytesIO(image_data))

        # # Get dimensions of the reference image
        # ref_width, ref_height = get_aspect_ratio(reference_image_path)

        # # Resize the image to match the reference image's dimensions
        # resized_image = image.resize((ref_width, ref_height), Image.LANCZOS)

        # # Generate a unique image ID
        # image_id = str(uuid.uuid4())

        # # Construct the file path
        # filename = f"{image_id}.{file_extension}"
        # filepath = os.path.join(save_dir, filename)

        # # Save the resized image
        # resized_image.save(filepath)

        return original_image
        # Return the image ID and extension
        return f"{image_id}.{file_extension}"

    except Exception as e:
        raise Exception(f"Error processing and saving the base64 image: {e}")

def get_aspect_ratio(image_path):
    with Image.open(image_path) as img:
        width, height = img.size
        print(f"helper width= {width} and height = {height}")
        return width,height
