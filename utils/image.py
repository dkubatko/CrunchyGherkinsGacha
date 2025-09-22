import io
import logging

from PIL import Image

logger = logging.getLogger(__name__)


class ImageUtil:
    @staticmethod
    def crop_to_content(image_bytes: bytes, force_radius_px: int = 5) -> bytes:
        """
        Crops the image to remove white and black borders/background.

        Args:
            image_bytes: The image data as bytes
            force_radius_px: Additional pixels to crop inside the content bounds to ensure all white is removed
        """
        try:
            # Convert bytes to PIL Image
            image = Image.open(io.BytesIO(image_bytes))

            # Convert to RGB if not already (to handle RGBA, etc.)
            if image.mode != "RGB":
                image = image.convert("RGB")

            # Define white and black color thresholds
            white_threshold = 240  # Pixels with all RGB values >= 240 are considered white
            black_threshold = 15  # Pixels with all RGB values <= 15 are considered black

            # Get image dimensions
            width, height = image.size

            # Find the bounding box of content that's neither white nor black
            left = width
            top = height
            right = 0
            bottom = 0

            # Scan all pixels to find the bounds of non-white and non-black content
            pixels = image.load()
            for y in range(height):
                for x in range(width):
                    r, g, b = pixels[x, y]
                    # Check if pixel is neither white nor black
                    is_white = (
                        r >= white_threshold and g >= white_threshold and b >= white_threshold
                    )
                    is_black = (
                        r <= black_threshold and g <= black_threshold and b <= black_threshold
                    )

                    # If pixel is neither white nor black, include it in bounding box
                    if not is_white and not is_black:
                        left = min(left, x)
                        right = max(right, x)
                        top = min(top, y)
                        bottom = max(bottom, y)

            # If no content found (only white/black pixels), return original image
            if left >= right or top >= bottom:
                logger.warning(
                    "No content found (only white/black pixels) in image, returning original"
                )
                return image_bytes

            # Apply force_radius_px to shrink bounds inward on each side
            original_left, original_top, original_right, original_bottom = left, top, right, bottom
            left = left + force_radius_px
            top = top + force_radius_px
            right = right - force_radius_px
            bottom = bottom - force_radius_px

            # Ensure we still have valid bounds after applying force_radius_px
            if left >= right or top >= bottom:
                logger.warning(
                    f"Force radius {force_radius_px} too large, would eliminate all content. Using original bounds."
                )
                # Revert to original bounds without force_radius_px
                left, top, right, bottom = (
                    original_left,
                    original_top,
                    original_right,
                    original_bottom,
                )

            # Crop the image to the bounding box
            cropped_image = image.crop((left, top, right + 1, bottom + 1))

            # Convert back to bytes
            output_buffer = io.BytesIO()
            cropped_image.save(output_buffer, format="PNG")
            processed_bytes = output_buffer.getvalue()

            logger.info(
                f"Image cropped from {width}x{height} to {cropped_image.size[0]}x{cropped_image.size[1]}"
            )
            return processed_bytes

        except Exception as e:
            logger.error(f"Error cropping image: {e}")
            # Return original image bytes if processing fails
            return image_bytes
