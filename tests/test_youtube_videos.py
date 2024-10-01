from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pytube.handlers.youtube import YT, PrepareVideoMetadata


@patch('src.youtube_videos.YT.check_macos_sequoia')
@patch('src.youtube_videos.conf')
@patch('src.youtube_videos.google_auth_oauthlib.flow.InstalledAppFlow')
@patch('src.youtube_videos.googleapiclient.discovery.build')
def test_get_authenticated_service(mock_build, mock_flow, mock_conf, mock_check_macos_sequoia):
    # Mock the configuration
    mock_conf.youtube.client_secrets_file = 'path/to/client_secrets.json'

    # Mock the flow
    mock_flow_instance = mock_flow.from_client_secrets_file.return_value
    mock_flow_instance.run_local_server.return_value = MagicMock()

    # Mock check_macos_sequoia
    mock_check_macos_sequoia.return_value = False

    # Create an instance of YT and call get_authenticated_service
    yt = YT()
    service = yt.get_authenticated_service()

    # Assertions
    mock_check_macos_sequoia.assert_called_once()
    mock_flow.from_client_secrets_file.assert_called_once_with('path/to/client_secrets.json', yt.scopes)
    mock_flow_instance.run_local_server.assert_called_once_with(port=0)
    mock_build.assert_called_once_with('youtube', 'v3', credentials=mock_flow_instance.run_local_server.return_value)
    assert service == mock_build.return_value


@patch('src.youtube_videos.conf')
@patch('src.youtube_videos.Credentials')
@patch('src.youtube_videos.InstalledAppFlow')
@patch('src.youtube_videos.build')
def test_get_authenticated_offline_service(mock_build, mock_flow, mock_credentials, mock_conf):
    # Mock the configuration
    mock_conf.youtube.client_secrets_file = 'path/to/client_secrets.json'
    mock_conf.dirs.root = Path('path/to/root')
    mock_conf.youtube.token_path = 'token.json'

    # Mock the token path
    token_path = mock_conf.dirs.root / mock_conf.youtube.token_path
    with patch.object(Path, 'exists', return_value=True):
        # Mock the credentials
        mock_creds = MagicMock()
        mock_credentials.from_authorized_user_file.return_value = mock_creds
        mock_creds.valid = True

        # Create an instance of YT and call get_authenticated_offline_service
        yt = YT()
        service = yt.get_authenticated_offline_service()

        # Assertions
        mock_credentials.from_authorized_user_file.assert_called_once_with(str(token_path), yt.scopes)
        mock_build.assert_called_once_with('youtube', 'v3', credentials=mock_creds)
        assert service == mock_build.return_value


@patch('src.youtube_videos.YT.get_authenticated_service')
@patch('src.youtube_videos.googleapiclient.discovery.build')
def test_list_all_videos(mock_build, mock_get_authenticated_service):
    # Mock the YouTube service
    mock_youtube = MagicMock()
    mock_get_authenticated_service.return_value = mock_youtube

    # Mock the API response
    mock_request = mock_youtube.search().list.return_value
    mock_request.execute.return_value = {
        "items": [{"id": "video1"}, {"id": "video2"}]
    }

    # Create an instance of YT and call list_all_videos
    yt = YT()
    videos = yt.list_all_videos('channel_id')

    # Assertions
    mock_youtube.search().list.assert_called_once_with(
        part="snippet",
        channelId='channel_id',
        maxResults=50,
        order="date",
        forMine=True
    )
    assert videos == [{"id": "video1"}, {"id": "video2"}]


def test_publish_dates_generator_with_delta():
    start = datetime(2023, 1, 1)
    delta = timedelta(days=1)
    generator = PrepareVideoMetadata.publish_dates_generator(start=start, delta=delta)

    dates = [next(generator) for _ in range(3)]
    assert dates == [
        datetime(2023, 1, 1),
        datetime(2023, 1, 2),
        datetime(2023, 1, 3)
    ]


def test_publish_dates_generator_with_end_and_steps():
    start = datetime(2023, 1, 1)
    end = datetime(2023, 1, 4)
    steps = 3
    generator = PrepareVideoMetadata.publish_dates_generator(start=start, end=end, steps=steps)

    dates = [next(generator) for _ in range(steps)]
    assert dates == [
        datetime(2023, 1, 1),
        datetime(2023, 1, 2),
        datetime(2023, 1, 3)
    ]


def test_publish_dates_generator_raises_value_error_without_end_or_delta():
    start = datetime(2023, 1, 1)
    with pytest.raises(ValueError,
                       match=r"Either end \(datetime\) or delta \(release every timeperiod\) must be provided"):
        list(PrepareVideoMetadata.publish_dates_generator(start=start))


def test_publish_dates_generator_raises_value_error_with_invalid_steps():
    start = datetime(2023, 1, 1)
    end = datetime(2023, 1, 4)
    with pytest.raises(ValueError, match="Steps must be an integer"):
        # noinspection PyTypeChecker
        list(PrepareVideoMetadata.publish_dates_generator(start=start, end=end, steps="invalid"))

    with pytest.raises(ValueError, match="Steps must be provided"):
        list(PrepareVideoMetadata.publish_dates_generator(start=start, end=end, steps=1))


@patch('src.youtube_videos.platform.system')
@patch('src.youtube_videos.platform.mac_ver')
def test_check_macos_sequoia(mock_mac_ver, mock_system):
    # Test case where macOS Sequoia is detected
    mock_system.return_value = "Darwin"
    mock_mac_ver.return_value = ("15.0", ("", "", ""), "")
    assert YT.check_macos_sequoia() is True

    # Test case where macOS Sequoia is not detected
    mock_system.return_value = "Darwin"
    mock_mac_ver.return_value = ("14.0", ("", "", ""), "")
    assert YT.check_macos_sequoia() is False

    # Test case where the system is not macOS
    mock_system.return_value = "Windows"
    mock_mac_ver.return_value = ("", ("", "", ""), "")
    assert YT.check_macos_sequoia() is False
