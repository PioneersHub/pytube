# Pre-Processing Metadata to `Records`

For each video a record is created.

### Detailed graph of the process

#### Collecting data from Pretalx

The data from Pretalx is collected via the `pythanis` library.

In `/records` the data is stored in JSON files named {pretalx id}.json.

``` mermaid
graph LR;

    P1[Pretalx-API Sessions];
    P2[Pretalx-API Speakers];
    R[(/records)];
    N[NLP Service];
    F((Records));
    P1 & P2 --load_all_confirmed_sessions, load_all_speakers, create_records--> F;
    F --- R;
    F --add_descriptions--> N;
    N --update--> R;    
```

#### Create Video Descriptions

The video descriptions are created from the records.

``` mermaid
graph LR;

    R[(Records)];
    V[(/video_records)];
    V2[(/…_records_updated)];
    F(("PrepareVideo
    Metadata"));
    F --- R;  
    F -- make_all_video_metadata, update_publish_dates --> V;  
    F -- send_all_video_metadata --> V2; 
    V -.move.- V2; 
```
Caveats:  
 - Scheduled videos need to be set 'private' (cannot be 'unlisted').

#### YouTube Check & Notification

The videos have a publishing date set. We need to monitor the release status and trigger Social Media posts
and emails to the speakers.

``` mermaid
graph LR;

    V2[(/…_records_updated)];
    V3[(/video_published)];
    F(("Publisher"));
    VS[YouTube];
    S[(/speaker_to_email)];
    L[(/linked_in_to_post)];
    C{online?};
    F -- check_status --> VS;
    V2 -.move.- V3;
    F -- process_recent_video_releases -> V2; 
    VS --> C --> |prepare_email| S;
    VS --> C --> |prepare_linkedin_post| L;
    VS --> C -.-> |move| V2;
```


In the final step send Social Media posts and emails to the speakers.

``` mermaid
graph LR;

    F(("Publisher"));
    S[(/speaker_to_email)];
    S2[(/speaker_to_email)];
    L[(/linked_in_to_post)];
    L2[(/linked_in_to_post)];
    F -- post_on_linked_id --> L;
    F -- email_speakers --> S;
    S -.move.- S2;
    L -.move.- L2;
    
```
