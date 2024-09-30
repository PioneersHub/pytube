# Welcome to PyTube

Manage and release conference videos on YouTube
using the talk and speaker information
from [Pretalx](https://github.com/pretalx/pretalx).

## Main Features

---

## High level process overview

1. Upload videos to YouTube
2. Collect data from Pretalx, store local JSON files `records`
3. Add descriptions to `records` via NLP
4. Process `records` to `video metadata` incl. publishing date, store in directory `video_records`
5. Update videos via API on YouTube with `video metadata`: move to `video_records_updated`
6. Confirm recently published videos: move to `video_published` and create Social Media posts and Email notifications
7. Send out Social Media posts and Emails

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

We always use the Pretix-ID for filenames.

## Preparations

Upload videos to YouTube, [for instructions see here](youtube.md).

## Limitations

Currently, a local storage is required for storage of metadata and managing the release status.
A future version should support a shared space or document database.