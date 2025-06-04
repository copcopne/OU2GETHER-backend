function togglePostFields() {
    const postTypeSelect = document.getElementById('id_post_type');
    if (!postTypeSelect) return;

    const mediaInline = document.getElementById('media-group');
    const pollInline = document.getElementById('poll-group');

    if (mediaInline) mediaInline.style.display = 'none';
    if (pollInline) pollInline.style.display = 'none';

    const selected = parseInt(postTypeSelect.value);
    if (selected === 1 && mediaInline) {
        mediaInline.style.display = 'block';
    } else if (selected === 2 && pollInline) {
        pollInline.style.display = 'block';
    }
}

document.addEventListener('DOMContentLoaded', function () {
    togglePostFields();

    const postTypeSelect = document.getElementById('id_post_type');
    if (postTypeSelect) {
        postTypeSelect.addEventListener('change', togglePostFields);
    }
});
