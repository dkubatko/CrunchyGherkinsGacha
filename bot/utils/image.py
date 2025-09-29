import io
import logging

from PIL import Image

logger = logging.getLogger(__name__)


class ImageUtil:
    @staticmethod
    def crop_to_content(image_bytes: bytes, force_radius_px: int = 5) -> bytes:
        """
        Crops the image to remove white, black, and gray-ish borders/background.

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

            # Define color thresholds
            white_threshold = 240  # Pixels with all RGB values >= 240 are considered white
            black_threshold = 15  # Pixels with all RGB values <= 15 are considered black
            gray_threshold = 40  # Maximum difference between RGB values for gray detection

            # Get image dimensions
            width, height = image.size

            # Find the bounding box of content that's neither white, black, nor gray
            left = width
            top = height
            right = 0
            bottom = 0

            # Scan all pixels to find the bounds of non-white, non-black, and non-gray content
            pixels = image.load()
            for y in range(height):
                for x in range(width):
                    r, g, b = pixels[x, y]

                    # Check if pixel is white
                    is_white = (
                        r >= white_threshold and g >= white_threshold and b >= white_threshold
                    )

                    # Check if pixel is black
                    is_black = (
                        r <= black_threshold and g <= black_threshold and b <= black_threshold
                    )

                    # Check if pixel is gray-ish (RGB values are close to each other)
                    rgb_values = [r, g, b]
                    is_gray = (max(rgb_values) - min(rgb_values)) <= gray_threshold

                    # If pixel is neither white, black, nor gray, include it in bounding box
                    if not is_white and not is_black and not is_gray:
                        left = min(left, x)
                        right = max(right, x)
                        top = min(top, y)
                        bottom = max(bottom, y)

            # If no content found (only white/black/gray pixels), return original image
            if left >= right or top >= bottom:
                logger.warning(
                    "No content found (only white/black/gray pixels) in image, returning original"
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

    @staticmethod
    def compress_to_fraction(image_bytes: bytes, scale_factor: float = 1 / 3) -> bytes:
        """Resize the image to a fraction of its original width and height."""
        if scale_factor <= 0:
            raise ValueError("scale_factor must be greater than 0")

        try:
            image = Image.open(io.BytesIO(image_bytes))
            original_format = image.format or "PNG"

            width, height = image.size
            target_width = max(1, int(width * scale_factor))
            target_height = max(1, int(height * scale_factor))

            if target_width == width and target_height == height:
                return image_bytes

            resized_image = image.resize((target_width, target_height), Image.LANCZOS)

            # Ensure consistent mode for saving while preserving alpha where possible
            if resized_image.mode not in ("RGB", "RGBA"):
                resized_image = resized_image.convert("RGBA" if image.mode == "RGBA" else "RGB")

            output_buffer = io.BytesIO()
            resized_image.save(output_buffer, format=original_format, optimize=True)
            logger.info(
                "Image compressed from %dx%d to %dx%d",
                width,
                height,
                target_width,
                target_height,
            )
            return output_buffer.getvalue()

        except Exception as exc:
            logger.error("Error compressing image: %s", exc)
            return image_bytes

    @staticmethod
    def crop_to_square(image_bytes: bytes) -> bytes:
        """Crop image to 1:1 aspect ratio (square) by cropping from the center."""
        try:
            image = Image.open(io.BytesIO(image_bytes))
            original_format = image.format or "PNG"

            width, height = image.size

            # If already square, return as is
            if width == height:
                return image_bytes

            # Determine the size of the square (smaller dimension)
            square_size = min(width, height)

            # Calculate crop coordinates to center the crop
            left = (width - square_size) // 2
            top = (height - square_size) // 2
            right = left + square_size
            bottom = top + square_size

            # Crop to square
            cropped_image = image.crop((left, top, right, bottom))

            # Convert back to bytes
            output_buffer = io.BytesIO()
            cropped_image.save(output_buffer, format=original_format)
            processed_bytes = output_buffer.getvalue()

            logger.info(
                f"Image cropped to square from {width}x{height} to {square_size}x{square_size}"
            )
            return processed_bytes

        except Exception as e:
            logger.error(f"Error cropping image to square: {e}")
            # Return original image bytes if processing fails
            return image_bytes
