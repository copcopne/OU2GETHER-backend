from cloudinary.uploader import upload
from ou2gether.models import PostMedia, CommentMedia

def handle_media_upload(files, comment_obj=None, post_obj=None):
    for file in files:
        type = 'image' if file.content_type.startswith('image/') else 'video'
        print(type)
        upload_result = upload(file, resource_type=type)
        path = f"{upload_result['resource_type']}/upload/v{upload_result['version']}/{upload_result['public_id']}.{upload_result['format']}"
        if comment_obj:
            CommentMedia.objects.create(
                comment=comment_obj,
                file=path,
                media_type=type
            )
            comment_obj.refresh_from_db()
        else:
            PostMedia.objects.create(
                post=post_obj,
                file=path,
                media_type=type
            )
            post_obj.refresh_from_db()
