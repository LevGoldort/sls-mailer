"""QR Code image generation and S3 upload utility"""
import qrcode
from io import BytesIO
import boto3
import os
from typing import Optional


def generate_qr_image(code: str, order_id: str, bucket_name: str = None) -> Optional[str]:
    """
    Генерирует QR код изображение и загружает в S3
    
    Args:
        code: Текст для QR кода (ticket code)
        order_id: ID заказа (для организации в S3)
        bucket_name: Имя S3 bucket (опционально, берется из env)
    
    Returns:
        Public URL QR кода или None при ошибке
    """
    try:
        # Get bucket name from env or parameter
        bucket = bucket_name or os.environ.get('QR_BUCKET', 'yallabalagan-ticket-media')
        region = os.environ.get('AWS_REGION', 'eu-north-1')

        print(f"Generating QR code for {code}, bucket: {bucket}, region: {region}")

        # Generate QR code image
        # Try PIL first, fallback to pure Python
        try:
            from PIL import Image
            import qrcode.image.pil
            image_factory = qrcode.image.pil.PilImage
            print("Using PIL image factory")
        except ImportError as e:
            print(f"PIL not available ({e}), falling back to PyPNG")
            # Fallback to pure python if PIL not available
            import qrcode.image.pure
            image_factory = qrcode.image.pure.PyPNGImage

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
            image_factory=image_factory,
        )
        qr.add_data(code)
        qr.make(fit=True)

        # Create image
        img = qr.make_image(fill_color="black", back_color="white")

        # Convert to bytes
        img_buffer = BytesIO()
        # PyPNG doesn't support format parameter
        if hasattr(img, 'save'):
            try:
                img.save(img_buffer, format='PNG')
            except TypeError:
                # PyPNG backend - no format parameter
                img.save(img_buffer)
        img_buffer.seek(0)
        
        # S3 key: qr-codes/{order_id}/{code}.png
        s3_key = f"qr-codes/{order_id}/{code}.png"

        print(f"Uploading QR code to S3: s3://{bucket}/{s3_key}")

        # Upload to S3
        try:
            s3_client = boto3.client('s3', region_name=region)
            s3_client.put_object(
                Bucket=bucket,
                Key=s3_key,
                Body=img_buffer.getvalue(),
                ContentType='image/png',
                CacheControl='max-age=31536000',  # 1 year cache
            )
            print(f"Successfully uploaded to S3")
        except Exception as s3_error:
            print(f"ERROR uploading to S3: {s3_error}")
            raise

        # Generate public URL
        url = f"https://{bucket}.s3.{region}.amazonaws.com/{s3_key}"

        print(f"QR code generated and uploaded: {url}")
        return url
        
    except Exception as e:
        print(f"Error generating QR code image: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

