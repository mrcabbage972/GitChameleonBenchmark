import inspect
import os
import json  # Changed from pickle
import sys

# --- Configuration ---
# Directory to save the persisted data
OUTPUT_DIR = "/app/persisted_data"
STOP_COMMENT = "# STOP INSTRUMENTATION"

# --- Create output directory if it doesn't exist ---
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _to_json_serializable(obj):
    """
    Recursively converts an object into a JSON-serializable format.
    Handles common scientific computing libraries and falls back gracefully.
    """
    # Check for specific library types only if the library is loaded
    numpy_is_loaded = 'numpy' in sys.modules
    torch_is_loaded = 'torch' in sys.modules

    if isinstance(obj, (int, float, str, bool, type(None))):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_to_json_serializable(item) for item in obj]
    if isinstance(obj, dict):
        return {str(k): _to_json_serializable(v) for k, v in obj.items()}

    # --- Numpy Conversion ---
    if numpy_is_loaded and isinstance(obj, sys.modules['numpy'].ndarray):
        return {
            "_type_": "numpy.ndarray",
            "dtype": str(obj.dtype),
            "shape": obj.shape,
            "data": obj.tolist()
        }

    # --- Torch Conversion ---
    if torch_is_loaded and isinstance(obj, sys.modules['torch'].Tensor):
        return {
            "_type_": "torch.Tensor",
            "dtype": str(obj.dtype),
            "shape": list(obj.shape),
            "device": str(obj.device),
            "data": obj.detach().cpu().numpy().tolist()
        }

    # --- Fallback for any other object ---
    try:
        return json.loads(json.dumps(obj))
    except (TypeError, OverflowError):
        return {
            "_type_": str(type(obj)),
            "value": str(obj)
        }


def _instrument_and_persist(func, outname):
    """
    Internal decorator to wrap a function, persisting its I/O to a JSON file.
    """
    func_name_for_wrapper = func.__name__

    def wrapper(*args, **kwargs):
        # Execute the original function to get the output
        output = func(*args, **kwargs)

        # --- MODIFIED: Filename now uses .json extension ---
        output_filename = os.path.join(OUTPUT_DIR, f"{outname}.{func_name_for_wrapper}.json")

        try:
            # --- MODIFIED: Convert all data to be JSON serializable ---
            serializable_payload = {
                "args": _to_json_serializable(args),
                "kwargs": _to_json_serializable(kwargs),
                "output": _to_json_serializable(output)
            }

            # --- MODIFIED: Use json.dump with indentation for readability ---
            with open(output_filename, "w") as f:
                json.dump(serializable_payload, f, indent=4)

            print(f"    [Persisted] I/O for '{func_name_for_wrapper}' -> {output_filename}")

        except Exception as e:
            print(f"    [Instrumentation Error] Could not write JSON for {func_name_for_wrapper}. Reason: {e}", file=sys.stderr)

        # Return the original output
        return output

    return wrapper


def activate_instrumentation(outname):
    """
    Activates instrumentation for all functions defined in the caller's file
    up to a line containing the STOP_COMMENT.
    """
    print("\n--- [INSTRUMENTATION STARTED] ---")
    # --- ADDED: Clarify the output format ---
    print(f"[*] Output Format: JSON")
    print(f"[*] Output Prefix: '{outname}'")


    # Get the frame of the code that called this function (the user's script)
    try:
        caller_frame = inspect.stack()[1]
        caller_filepath = caller_frame.filename
        caller_globals = caller_frame.frame.f_globals
        caller_module_name = caller_globals.get('__name__')
    except IndexError:
        print("[Instrumentation Error] Could not inspect the caller's stack.", file=sys.stderr)
        return
    finally:
        # Frames can create reference cycles, so clean it up.
        del caller_frame

    # Find the line number of the stop comment
    stop_line_number = float('inf')
    try:
        with open(caller_filepath, 'r') as f:
            for i, line in enumerate(f):
                if STOP_COMMENT in line:
                    stop_line_number = i + 1
                    break
    except FileNotFoundError:
        print(f"[Instrumentation Error] Could not find source file {caller_filepath}", file=sys.stderr)
        return
    
    if stop_line_number == float('inf'):
        print(f"[*] No '{STOP_COMMENT}' found. Will instrument all functions in {os.path.basename(caller_filepath)}.")
    else:
        print(f"[*] Found stop comment on line {stop_line_number}. Instrumenting functions defined before this line.")

    # Find and decorate functions in the caller's scope
    instrumented_count = 0
    for name, obj in list(caller_globals.items()):
        if not (inspect.isfunction(obj) and obj.__module__ == caller_module_name):
            continue

        try:
            _source_lines, func_start_line = inspect.getsourcelines(obj)
            
            if func_start_line < stop_line_number:
                # Apply the decorator, passing the outname prefix
                caller_globals[name] = _instrument_and_persist(obj, outname)
                print(f"    - Wrapping function: '{name}' (defined on line {func_start_line})")
                instrumented_count += 1

        except (TypeError, OSError):
            continue

    if instrumented_count == 0:
        print("[*] No functions found to instrument in the target scope.")
    print("--- [INSTRUMENTATION FINISHED] ---\n")