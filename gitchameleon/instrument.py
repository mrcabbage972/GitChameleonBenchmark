import inspect
import os
import pickle
import sys

# --- Configuration ---
# Directory to save the persisted data
OUTPUT_DIR = "persisted_data"
STOP_COMMENT = "# STOP INSTRUMENTATION"

# --- Create output directory if it doesn't exist ---
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _instrument_and_persist(func):
    """
    Internal decorator to wrap a function, persisting its inputs and output.
    This is the logic that will be applied to the target functions.
    """
    func_name_for_wrapper = func.__name__

    def wrapper(*args, **kwargs):
        # Execute the original function to get the output
        output = func(*args, **kwargs)

        # Get module and function details
        try:
            module_name = inspect.getmodule(func).__name__
        except AttributeError:
            module_name = "unknown_module"

        output_filename = os.path.join(OUTPUT_DIR, f"{module_name}.{func_name_for_wrapper}.pkl")

        # Persist the inputs and output
        try:
            with open(output_filename, "wb") as f:
                pickle.dump({
                    "args": args,
                    "kwargs": kwargs,
                    "output": output
                }, f)
            # --- ADDED: Print statement confirming persistence ---
            print(f"    [Persisted] I/O for '{func_name_for_wrapper}' -> {output_filename}")

        except (pickle.PicklingError, TypeError) as e:
            print(f"    [Instrumentation Error] Could not pickle I/O for {func_name_for_wrapper}. Reason: {e}", file=sys.stderr)

        # Return the original output
        return output

    return wrapper


def activate_instrumentation():
    """
    Activates instrumentation for all functions defined in the caller's file
    up to a line containing the STOP_COMMENT.
    """
    # --- ADDED: Start message ---
    print("\n--- [INSTRUMENTATION STARTED] ---")

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

    # --- Step 1: Find the line number of the stop comment ---
    stop_line_number = float('inf')
    try:
        with open(caller_filepath, 'r') as f:
            for i, line in enumerate(f):
                if STOP_COMMENT in line:
                    stop_line_number = i + 1 # line numbers are 1-based
                    break
    except FileNotFoundError:
        print(f"[Instrumentation Error] Could not find source file {caller_filepath}", file=sys.stderr)
        return
    
    # --- ADDED: Boundary message ---
    if stop_line_number == float('inf'):
        print(f"[*] No '{STOP_COMMENT}' found. Will instrument all functions in {os.path.basename(caller_filepath)}.")
    else:
        print(f"[*] Found stop comment on line {stop_line_number}. Instrumenting functions defined before this line.")

    # --- Step 2: Find and decorate functions in the caller's scope ---
    instrumented_count = 0
    # Iterate over a copy of the items, as we'll be modifying the dictionary
    for name, obj in list(caller_globals.items()):
        # We only want to instrument functions that were DEFINED in the caller's module
        if not (inspect.isfunction(obj) and obj.__module__ == caller_module_name):
            continue

        try:
            _source_lines, func_start_line = inspect.getsourcelines(obj)
            
            # --- Step 3: Apply the decorator if the function is defined before the stop comment ---
            if func_start_line < stop_line_number:
                caller_globals[name] = _instrument_and_persist(obj)
                # --- ADDED: Print statement for what was instrumented ---
                print(f"    - Wrapping function: '{name}' (defined on line {func_start_line})")
                instrumented_count += 1

        except (TypeError, OSError):
            continue

    # --- ADDED: End message ---
    if instrumented_count == 0:
        print("[*] No functions found to instrument in the target scope.")
    print("--- [INSTRUMENTATION FINISHED] ---\n")