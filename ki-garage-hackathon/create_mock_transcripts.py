#!/usr/bin/env python3
"""
Create mock transcript folders and files for dummy talks
"""

import os
from pathlib import Path

# Base path for transcriptions
base_path = Path(
    "/Users/REDACTED/Documents/development/ki-garage-hackathon/pytube_data/pyconde-pydata-2025/transcriptions"
)

# Mock data for each dummy talk
mock_talks = [
    {
        "talk_id": "DUMMY01",
        "folder_name": "001-Building_Scalable_Python_Applications_with_AsyncIO_[DUMMY01]",
        "transcript": """============================================================
AUDIO TRANSCRIPTION REPORT
============================================================
File: 001-Building_Scalable_Python_Applications_with_AsyncIO_[DUMMY01].mp3
Duration: 2400.00 seconds
Processed: 2025-01-26 10:00:00
------------------------------------------------------------
FULL TRANSCRIPTION:

Welcome everyone to this talk on building scalable Python applications with AsyncIO. 
I'm Dr. Jane Smith, and today we'll explore how to leverage Python's asynchronous 
capabilities to build highly performant applications.

First, let's understand what AsyncIO is. AsyncIO is Python's built-in library for 
writing concurrent code using the async/await syntax. It's particularly useful when 
dealing with I/O-bound operations like network requests, file operations, or database queries.

The key concepts we'll cover today include:
- Event loops and how they work
- Coroutines and async functions
- Tasks and concurrent execution
- Error handling in async contexts
- Best practices for production systems

Let me show you a simple example of AsyncIO in action...

[Content continues with code examples and explanations about AsyncIO patterns, 
performance optimizations, and real-world use cases in building scalable systems]

Thank you for attending this session. Remember, AsyncIO is a powerful tool, but 
use it wisely - not every problem needs an asynchronous solution.

------------------------------------------------------------
DETAILED SEGMENTS:

1. [00:00 - 05:00] Introduction and Overview
2. [05:00 - 15:00] AsyncIO Fundamentals
3. [15:00 - 25:00] Advanced Patterns
4. [25:00 - 35:00] Production Best Practices
5. [35:00 - 40:00] Q&A Session
""",
    },
    {
        "talk_id": "DUMMY02",
        "folder_name": "002-Machine_Learning_in_Production_Best_Practices_[DUMMY02]",
        "transcript": """============================================================
AUDIO TRANSCRIPTION REPORT
============================================================
File: 002-Machine_Learning_in_Production_Best_Practices_[DUMMY02].mp3
Duration: 3000.00 seconds
Processed: 2025-01-26 11:00:00
------------------------------------------------------------
FULL TRANSCRIPTION:

Good morning everyone. Today we're going to talk about deploying machine learning 
models in production environments. This is a critical topic that bridges the gap 
between data science and software engineering.

The main challenges we face when moving from notebooks to production include:
- Model versioning and reproducibility
- Monitoring and observability
- Scaling and performance optimization
- Data drift detection
- A/B testing and gradual rollouts

I'll share real-world examples from deploying models at scale, including lessons 
learned from failures and successes. We'll look at tools like MLflow, Kubeflow, 
and custom solutions built on top of Kubernetes.

One key principle is to treat your ML models as first-class software artifacts. 
This means proper testing, CI/CD pipelines, and monitoring just like any other 
production service.

[Discussion continues with specific examples of ML pipelines, monitoring strategies, 
and best practices for maintaining models in production environments]

Remember: a model that performs well in development but fails in production is 
worse than no model at all. Always plan for production from day one.

------------------------------------------------------------
DETAILED SEGMENTS:

1. [00:00 - 10:00] Introduction to MLOps
2. [10:00 - 20:00] Model Deployment Strategies
3. [20:00 - 35:00] Monitoring and Maintenance
4. [35:00 - 45:00] Case Studies
5. [45:00 - 50:00] Q&A and Discussion
""",
    },
    {
        "talk_id": "DUMMY03",
        "folder_name": "003-Data_Visualization_with_Python_Beyond_Matplotlib_[DUMMY03]",
        "transcript": """============================================================
AUDIO TRANSCRIPTION REPORT
============================================================
File: 003-Data_Visualization_with_Python_Beyond_Matplotlib_[DUMMY03].mp3
Duration: 2700.00 seconds
Processed: 2025-01-26 12:00:00
------------------------------------------------------------
FULL TRANSCRIPTION:

Hello everyone! Today we're going beyond Matplotlib to explore the rich ecosystem 
of data visualization libraries in Python. While Matplotlib is powerful, there are 
many other tools that can make your visualizations more interactive, beautiful, 
and easier to create.

We'll explore several libraries today:
- Plotly for interactive visualizations
- Seaborn for statistical graphics
- Altair for declarative visualization
- Bokeh for web-ready plots
- HoloViews for data analysis

Each library has its strengths and ideal use cases. I'll demonstrate when to use 
each one with practical examples from real data science projects.

Let's start with Plotly. One of its biggest advantages is the ability to create 
interactive plots that users can explore by zooming, panning, and hovering for details...

[Continues with live coding demonstrations, comparing different libraries for various 
visualization tasks, and discussing performance considerations]

The key takeaway is that you should choose the right tool for your specific needs. 
Consider factors like interactivity requirements, output format, performance, and 
ease of use when selecting a visualization library.

------------------------------------------------------------
DETAILED SEGMENTS:

1. [00:00 - 05:00] Introduction and Overview
2. [05:00 - 15:00] Plotly Deep Dive
3. [15:00 - 25:00] Statistical Visualization with Seaborn
4. [25:00 - 35:00] Web Visualizations with Bokeh
5. [35:00 - 45:00] Comparing All Libraries
""",
    },
]

print("🎬 Creating mock transcript folders and files...\n")

for talk in mock_talks:
    # Create folder
    folder_path = base_path / talk["folder_name"]
    folder_path.mkdir(parents=True, exist_ok=True)

    # Create transcript.txt
    transcript_file = folder_path / "transcript.txt"
    transcript_file.write_text(talk["transcript"])

    # Also create the JSON format that's in the real folders
    transcript_json = folder_path / "transcript.json"
    json_content = {"text": talk["transcript"], "segments": [], "language": "en"}
    import json

    transcript_json.write_text(json.dumps(json_content, indent=2))

    print(f"✅ Created transcript for {talk['talk_id']}:")
    print(f"   📁 {folder_path}")
    print(f"   📄 transcript.txt")
    print(f"   📄 transcript.json")

print("\n✨ Mock transcripts created successfully!")
print("\n📝 The n8n workflow will now be able to:")
print("1. Find the transcript folders (by looking for [DUMMY01], etc.)")
print("2. Read the transcript.txt files")
print("3. Generate AI content based on the mock transcripts")
print("\n🚀 Ready to run the workflow!")
