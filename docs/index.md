# Welcome to PyTube

Manage and release conference videos on YouTube
using the talk and speaker information
from [Pretalx](https://github.com/pretalx/pretalx).

## Main Features

* Manage the release of videos on YouTube:
    * Video descriptions
    * Publishing date
    * Monitoring of the release status and triggering of Social Media posts
    * Management of videos in multiple channels
* Create descriptions based on the data in Pretalx with NLP
* Create and post Social Media posts
* Email notifications to speakers

---

## High level process overview

1. Upload videos to YouTube
2. Collect data from Pretalx, store local JSON files `records`
3. Add descriptions to `records` via NLP
4. Process `records` to `video metadata` incl. publishing date, store in directory `video_records`
5. Update videos via API on YouTube with `video metadata`: move to `video_records_updated`
6. Confirm recently published videos: move to `video_published` and create Social Media posts and Email notifications
7. Send out Social Media posts and Emails

---

### Simplified graph of the process

``` mermaid
graph LR;

    P[Pretalx];
    R[Records];
    N[descriptions];
    V[Video metadata];
    F((Process));
    G((Process));
    H((Process));
    VS[YouTube];
    S[Post/Email];
    P ---> R;
    R --- N --add --> R;
    F --- R;
    F --- V;
    G --- V;
    G --- VS;
    H --- VS;
    H --- S;
    
```

## Conventions

For file naming, always use the Pretix-ID is used.

For each status a separate directory is used. Move the files to the next status directory after successful processing.

## Preparations

Upload videos to YouTube, [for instructions see here](youtube.md).

### Configration

There is a general configuration file `config.yaml` that provides the general structure.

Individual configurations are stored in the local file `config_local.yaml` which must never be shared:

* Storage locations
* Pretalx
    * Event information
    * Custom assignments of Pretalx ID to a release channel (e.g., PyCon DE / PyData)
* YouTube
    * credentials
    * channels
* OpenAI: credentials
* Other:
    * Vimeo API access (optional)
    * Google Spreadsheets (optional). Often used for managing custom information like opt-outs.

!!! note
    Pretalx access is provided via `pythanis` which stores the credentials in a separate local file

### Credentials for Pythanis

Pretalx is used to interact with:

1. Pretalx
2. Google Spreadsheets
3. Helpdesk (to send Emails)

[See here](https://florianwilhelm.info/pytanis/latest/usage/installation/#retrieving-the-credentials-and-tokens)
how to add credentials.

## Limitations

Currently, a local storage is required for storage of metadata and managing the release status.  
A future version should support a shared space or document database.

Sending Emails is currently only supported via the Helpdesk API.  
Other ways to send emails should be supported in the future.