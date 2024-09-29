import datetime
from unittest.mock import MagicMock, mock_open, patch

import pytest

from src.job import Publisher


@pytest.fixture
def mock_dependencies(mocker):
    mock_yt = mocker.patch('src.job.YT').return_value
    mock_prepare_video_metadata = mocker.patch('src.job.PrepareVideoMetadata').return_value
    mock_omegaconf_load = mocker.patch('src.job.OmegaConf.load').return_value
    mock_omegaconf_load.linkedin = MagicMock()
    publisher = Publisher(destination_channel='test_channel')
    return publisher, mock_yt, mock_prepare_video_metadata


@patch('src.job.datetime')
def test_release_on_youtube_now(mock_datetime, mock_dependencies):
    publisher, mock_yt, _ = mock_dependencies
    mock_datetime.datetime.now.return_value = datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC)
    mock_request = mock_yt.youtube.videos().update.return_value
    mock_request.execute.return_value = {'status': 'success'}

    response = publisher.release_on_youtube_now('video_id', 'title', 'description', 'category_id')

    assert response == {'status': 'success'}
    mock_yt.youtube.videos().update.assert_called_once()


@patch('src.job.Path.open', new_callable=mock_open)
@patch('src.job.LinkedIn.register_image')
@patch('src.job.LinkedIn.upload_media')
def test_media_share(mock_upload_media, mock_register_image, mock_open, mock_dependencies):
    publisher, _, _ = mock_dependencies
    mock_register_image.return_value = {'value': {'image': 'asset_urn', 'uploadUrl': 'upload_url'}}
    mock_upload_media.return_value = 'upload_response'
    data = {'pretalx_id': 'video1'}

    response = publisher.media_share(data)

    assert response == 'upload_response'
    mock_register_image.assert_called_once()
    mock_upload_media.assert_called_once()
