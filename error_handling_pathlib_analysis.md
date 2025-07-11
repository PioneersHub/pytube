# Error Handling and Pathlib Usage Analysis

## Executive Summary

After analyzing the PyTube codebase, I found a mix of good and problematic patterns regarding error handling and file path operations. While pathlib is widely adopted, there are several areas that need improvement.

## 1. Error Handling Patterns

### ✅ Good Patterns Found

1. **Specific exception handling in records.py**:
   ```python
   try:
       subs_count, subs = self.pretalx_client.submissions(...)
   except Exception as e:
       logger.error(f"Failed to fetch submissions from Pretalx: {e}")
       raise RuntimeError(f"Unable to connect to Pretalx API: {e}") from e
   ```
   - Uses specific error messages
   - Re-raises with context using `from e`
   - Logs before raising

2. **Graceful degradation in status.py**:
   ```python
   try:
       published_dir = event_dir / "video_published"
       # ... processing ...
   except Exception:
       pass  # Skip if can't access published directory
   ```
   - Handles non-critical failures gracefully

3. **Error context in handlers/publisher.py**:
   ```python
   except Exception as e:
       logger.error(f"Failed to check video status: {str(e)}")
       return
   ```
   - Logs errors with context
   - Returns gracefully instead of crashing

### ❌ Problematic Patterns Found

1. **Print statements instead of logging**:
   - Found in 20 files including CLI modules
   - Many CLI files use `print()` directly instead of `console.print()` or logging
   - Example: `src/manager/cli/assistant.py`, `src/manager/cli/workflow.py`

2. **Missing error context in video_processor/presentation_detector.py**:
   ```python
   except Exception as e:
       logger.info(f"Error generating processing plan: {str(e)}")
       traceback.print_exc()  # Should use logger
   ```
   - Uses `traceback.print_exc()` instead of logger
   - Should use `logger.exception()` for proper error tracking

## 2. Pathlib Usage

### ✅ Good Patterns Found

1. **Consistent Path usage**:
   - 24 files import `from pathlib import Path`
   - Most file operations use Path objects correctly
   - Example from handlers/records.py:
   ```python
   self.event_dir = self._get_event_dir()
   self.records: Path = self.event_dir / "records"
   self.records.mkdir(parents=True, exist_ok=True)
   ```

2. **Path methods used properly**:
   ```python
   # Good examples from handlers/publisher.py
   video_record_path.read_text()
   video_record_path.write_text(video_record.model_dump_json(indent=4))
   video_record_path.rename(self.youtube_client.video_records_path_published / record_path.name)
   ```

### ❌ Problematic Patterns Found

1. **os.path usage in presentation_detector.py**:
   ```python
   # Line 38-39
   if not os.path.isdir(input_folder):
       logger.info(f"Error: Input folder does not exist: {input_folder}")
   
   # Line 52-57
   pattern = os.path.join(input_folder, f"*{ext}")
   pattern = os.path.join(input_folder, f"*{ext.upper()}")
   
   # Line 290
   if not break_images_dir or not os.path.isdir(break_images_dir):
   
   # Line 296-298
   image_files = (
       glob.glob(os.path.join(break_images_dir, "*.jpg"))
       + glob.glob(os.path.join(break_images_dir, "*.png"))
   )
   
   # Line 316
   logger.info(f"  Loaded: {os.path.basename(img_path)}")
   
   # Line 418
   os.makedirs(detected_dir, exist_ok=True)
   ```
   - Should use `Path.is_dir()`, `Path.glob()`, `Path.name`, `Path.mkdir()`

2. **File operations without context managers**:
   ```python
   # Multiple files use .open() without 'with' statement
   json.dump(pretalx_yt_map, output_file.open("w"), indent=4)  # youtube.py line 365
   json.dump(confirmed_map, (self.event_dir / "confirmed_sessions_map.json").open("w"), indent=4)  # records.py line 212
   ```
   - Should use `with open()` for proper resource management

3. **os.system() usage in presentation_detector.py**:
   ```python
   # Lines 824, 832
   os.system(video_cmd)
   os.system(audio_cmd)
   ```
   - Should use `subprocess.run()` for better error handling and security

## 3. File Operations

### ✅ Good Patterns

1. **Context managers used in some places**:
   ```python
   with open(self.processing_plan_path, "w") as f:
       json.dump(processing_plan, f, indent=2)
   ```

### ❌ Issues Found

1. **Inconsistent encoding specification**:
   - Many file operations don't specify encoding
   - Should always use `encoding='utf-8'` for text files

2. **Missing error handling for file operations**:
   - Many file reads/writes don't handle potential IOError
   - Example: direct `.read_text()` without try/except

## Recommendations

### High Priority Fixes

1. **Replace all os.path usage in presentation_detector.py**:
   ```python
   # Replace
   if not os.path.isdir(input_folder):
   # With
   if not Path(input_folder).is_dir():
   
   # Replace
   pattern = os.path.join(input_folder, f"*{ext}")
   # With
   pattern = Path(input_folder) / f"*{ext}"
   ```

2. **Use context managers for all file operations**:
   ```python
   # Replace
   json.dump(data, path.open("w"), indent=4)
   # With
   with path.open("w", encoding="utf-8") as f:
       json.dump(data, f, indent=4)
   ```

3. **Replace print() with proper logging/console**:
   - In CLI files: use `console.print()` from Rich
   - In non-CLI files: use `logger.info()` or appropriate log level

### Medium Priority

1. **Add error context to all exceptions**:
   ```python
   except SpecificError as e:
       logger.error(f"Failed to do X: {e}")
       raise NewError(f"Could not complete operation: {e}") from e
   ```

2. **Replace os.system() with subprocess**:
   ```python
   # Replace
   os.system(cmd)
   # With
   import subprocess
   result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
   if result.returncode != 0:
       logger.error(f"Command failed: {result.stderr}")
   ```

### Low Priority

1. **Add type hints for Path objects**:
   ```python
   def process_file(file_path: Path) -> None:
   ```

2. **Use logger.exception() in except blocks**:
   ```python
   except Exception:
       logger.exception("Unexpected error in processing")
   ```

## Files Requiring Immediate Attention

1. **src/video_processor/presentation_detector.py** - Multiple os.path usages
2. **CLI files with print() statements** - Should use Rich console
3. **File operations without context managers** - Throughout the codebase

## Summary Statistics

- **os.path usage**: 1 file (presentation_detector.py)
- **print() usage**: 20 files 
- **pathlib imports**: 24 files ✅
- **Bare except clauses**: 0 ✅
- **Files needing context managers**: Multiple instances across handlers and CLI