import io
import logging

from PIL import Image

logger = logging.getLogger(__name__)

JPEG_QUALITY = 95


class ImageUtil:
    @staticmethod
    def to_jpeg(image_bytes: bytes, quality: int = JPEG_QUALITY) -> bytes:
        """Convert any image to JPEG at consistent quality.

        Strips alpha channel (RGBA → RGB) since JPEG doesn't support
        transparency.  Already-valid JPEGs are returned unchanged to
        avoid generational quality loss.
        """
        try:
            image = Image.open(io.BytesIO(image_bytes))
            if image.format == "JPEG" and image.mode == "RGB":
                return image_bytes
            if image.mode != "RGB":
                image = image.convert("RGB")
            buf = io.BytesIO()
            image.save(buf, format="JPEG", quality=quality)
            result = buf.getvalue()
            logger.info(
                "Converted image to JPEG (%dx%d, %d bytes)",
                image.size[0], image.size[1], len(result),
            )
            return result
        except Exception as e:
            logger.error("Error converting to JPEG: %s", e)
            return image_bytes

    @staticmethod
    def crop_to_content(image_bytes: bytes, force_radius_px: int = 0) -> bytes:
        """
        Lightly crop uniform borders from image edges.

        Scans rows/columns from each edge inward, stopping at the first
        row/column where content is detected (i.e., not uniformly background).
        Much less aggressive than per-pixel scanning — only removes truly
        blank borders that Gemini sometimes adds.
        """
        try:
            image = Image.open(io.BytesIO(image_bytes))
            if image.mode != "RGB":
                rgb_image = image.convert("RGB")
            else:
                rgb_image = image

            pixels = rgb_image.load()
            width, height = rgb_image.size

            def is_background_pixel(r, g, b):
                """Check if a pixel is likely background (white, black, or near-gray)."""
                is_white = r >= 245 and g >= 245 and b >= 245
                is_black = r <= 10 and g <= 10 and b <= 10
                return is_white or is_black

            def is_uniform_row(y, threshold=0.95):
                """Check if a row is mostly background pixels."""
                bg_count = sum(1 for x in range(width) if is_background_pixel(*pixels[x, y]))
                return bg_count / width >= threshold

            def is_uniform_col(x, threshold=0.95):
                """Check if a column is mostly background pixels."""
                bg_count = sum(1 for y in range(height) if is_background_pixel(*pixels[x, y]))
                return bg_count / height >= threshold

            # Scan from each edge inward
            top = 0
            while top < height and is_uniform_row(top):
                top += 1

            bottom = height - 1
            while bottom > top and is_uniform_row(bottom):
                bottom -= 1

            left = 0
            while left < width and is_uniform_col(left):
                left += 1

            right = width - 1
            while right > left and is_uniform_col(right):
                right -= 1

            # Apply optional additional inward margin
            if force_radius_px > 0:
                top = min(top + force_radius_px, bottom)
                bottom = max(bottom - force_radius_px, top)
                left = min(left + force_radius_px, right)
                right = max(right - force_radius_px, left)

            # Only crop if we found meaningful borders to remove
            if top == 0 and bottom == height - 1 and left == 0 and right == width - 1:
                return image_bytes

            # Crop the original image (preserve alpha if present)
            cropped = image.crop((left, top, right + 1, bottom + 1))

            output_format = image.format or "JPEG"
            if output_format.upper() in ("JPEG", "JPG") and cropped.mode == "RGBA":
                cropped = cropped.convert("RGB")

            output_buffer = io.BytesIO()
            save_kwargs: dict = {"format": output_format}
            if output_format.upper() in ("JPEG", "JPG"):
                save_kwargs["quality"] = JPEG_QUALITY
            cropped.save(output_buffer, **save_kwargs)

            logger.info(
                f"Image cropped from {width}x{height} to {cropped.size[0]}x{cropped.size[1]}"
            )
            return output_buffer.getvalue()

        except Exception as e:
            logger.error(f"Error cropping image: {e}")
            return image_bytes

    @staticmethod
    def compress_to_fraction(image_bytes: bytes, scale_factor: float = 1 / 4) -> bytes:
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
            if original_format.upper() in ("JPEG", "JPG"):
                if resized_image.mode != "RGB":
                    resized_image = resized_image.convert("RGB")
            elif resized_image.mode not in ("RGB", "RGBA"):
                resized_image = resized_image.convert("RGBA" if image.mode == "RGBA" else "RGB")

            output_buffer = io.BytesIO()
            save_kwargs: dict = {"format": original_format}
            if original_format.upper() in ("JPEG", "JPG"):
                save_kwargs["quality"] = JPEG_QUALITY
            else:
                save_kwargs["optimize"] = True
            resized_image.save(output_buffer, **save_kwargs)
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
    def crop_to_aspect_ratio(image_bytes: bytes, target_ratio: float) -> bytes:
        """
        Center-crop image to target aspect ratio (width/height).

        Examples:
            crop_to_aspect_ratio(img, 5/7)  # Portrait card
            crop_to_aspect_ratio(img, 1.0)   # Square (same as crop_to_square)
        """
        try:
            image = Image.open(io.BytesIO(image_bytes))
            original_format = image.format or "PNG"
            width, height = image.size

            current_ratio = width / height

            if abs(current_ratio - target_ratio) < 0.01:
                return image_bytes

            if current_ratio > target_ratio:
                # Image is too wide — crop width
                new_width = int(height * target_ratio)
                left = (width - new_width) // 2
                crop_box = (left, 0, left + new_width, height)
            else:
                # Image is too tall — crop height
                new_height = int(width / target_ratio)
                top = (height - new_height) // 2
                crop_box = (0, top, width, top + new_height)

            cropped = image.crop(crop_box)

            if original_format.upper() in ("JPEG", "JPG") and cropped.mode == "RGBA":
                cropped = cropped.convert("RGB")

            output_buffer = io.BytesIO()
            save_kwargs: dict = {"format": original_format}
            if original_format.upper() in ("JPEG", "JPG"):
                save_kwargs["quality"] = JPEG_QUALITY
            cropped.save(output_buffer, **save_kwargs)

            logger.info(
                f"Image cropped to ratio {target_ratio:.2f} from {width}x{height} to {cropped.size[0]}x{cropped.size[1]}"
            )
            return output_buffer.getvalue()

        except Exception as e:
            logger.error(f"Error cropping to aspect ratio: {e}")
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

            if original_format.upper() in ("JPEG", "JPG") and cropped_image.mode == "RGBA":
                cropped_image = cropped_image.convert("RGB")

            # Convert back to bytes
            output_buffer = io.BytesIO()
            save_kwargs: dict = {"format": original_format}
            if original_format.upper() in ("JPEG", "JPG"):
                save_kwargs["quality"] = JPEG_QUALITY
            cropped_image.save(output_buffer, **save_kwargs)
            processed_bytes = output_buffer.getvalue()

            logger.info(
                f"Image cropped to square from {width}x{height} to {square_size}x{square_size}"
            )
            return processed_bytes

        except Exception as e:
            logger.error(f"Error cropping image to square: {e}")
            # Return original image bytes if processing fails
            return image_bytes

    @staticmethod
    def resize_to_dimensions(
        image_bytes: bytes,
        target_width: int,
        target_height: int,
        output_format: str | None = None,
    ) -> bytes:
        """
        Resize image to specific dimensions.

        Args:
            image_bytes: The image data as bytes
            target_width: Target width in pixels
            target_height: Target height in pixels
            output_format: Explicit output format (e.g. ``"JPEG"``).
                           If ``None``, preserves the input format (falls back to PNG).

        Returns:
            Resized image as bytes
        """
        try:
            image = Image.open(io.BytesIO(image_bytes))
            fmt = output_format or image.format or "PNG"

            width, height = image.size

            # If already the target size, return as is
            if width == target_width and height == target_height:
                if output_format is None:
                    return image_bytes
                # Still need to re-encode if caller requested a specific format
                # and the image might not be in that format already
                if image.format and image.format.upper() == fmt.upper():
                    return image_bytes

            # Resize using high-quality LANCZOS resampling
            resized_image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)

            if fmt.upper() in ("JPEG", "JPG") and resized_image.mode != "RGB":
                resized_image = resized_image.convert("RGB")

            # Convert back to bytes
            output_buffer = io.BytesIO()
            save_kwargs: dict = {"format": fmt}
            if fmt.upper() in ("JPEG", "JPG"):
                save_kwargs["quality"] = JPEG_QUALITY
            else:
                save_kwargs["optimize"] = True
            resized_image.save(output_buffer, **save_kwargs)
            processed_bytes = output_buffer.getvalue()

            logger.info(f"Image resized from {width}x{height} to {target_width}x{target_height}")
            return processed_bytes

        except Exception as e:
            logger.error(f"Error resizing image to {target_width}x{target_height}: {e}")
            # Return original image bytes if processing fails
            return image_bytes
