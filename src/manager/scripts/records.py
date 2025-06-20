"""
This module loads all metadata from pretalx

Make sure to put the mapping of for custom questions in config_local.yaml

"""

from manager import conf
from manager.handlers import Records

if __name__ == "__main__":
    questions_map = conf.pretalx.questions_map
    r = Records(qmap=questions_map)

    # Track statistics
    sessions_count = 0
    speakers_count = 0

    # Load sessions and speakers
    print("\n" + "=" * 60)
    print("PyTube Records Manager - Fetching data from Pretalx")
    print("=" * 60 + "\n")

    r.load_all_confirmed_sessions()
    sessions_count = len(r.confirmed_sessions_map)
    print(f"✓ Loaded {sessions_count} confirmed sessions from Pretalx\n")

    r.load_all_speakers()
    speakers_count = len(r.speakers_map)
    print(f"✓ Loaded {speakers_count} speakers from Pretalx\n")

    # Create records
    print("Creating session records...")
    record_stats = r.create_records()
    print(f"✓ Records created: {record_stats['created']} new, {record_stats['updated']} updated\n")

    # Add descriptions
    print("Generating AI descriptions...")
    desc_stats = r.add_descriptions(replace=False)
    print(f"✓ Descriptions: {desc_stats['added']} added, {desc_stats['skipped']} skipped\n")

    # Final summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Sessions fetched from Pretalx: {sessions_count}")
    print(f"Speakers fetched from Pretalx: {speakers_count}")
    print(f"New records created:           {record_stats['created']}")
    print(f"Existing records updated:      {record_stats['updated']}")
    print(f"Total records processed:       {record_stats['total']}")
    print(f"Descriptions added:            {desc_stats['added']}")
    print(f"Descriptions skipped:          {desc_stats['skipped']}")
    print("\n✅ All operations completed successfully!\n")
