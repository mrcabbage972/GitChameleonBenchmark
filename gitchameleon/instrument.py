import inspect
import os
import pickle
import sys

# --- Configuration ---
# Directory to save the persisted data
OUTPUT_DIR = "persisted_data"
# Prefix for modules to be instrumented
MODULE_PREFIX = "sample_"

# --- Create output directory if it doesn't exist ---
os.makedirs(OUTPUT_DIR, exist_ok=True)

def persist_inputs_and_output(func):
    """
    A decorator that persists the input arguments and the output of a function to a file.
    """
    def wrapper(*args, **kwargs):
        # --- Execute the original function and capture the output ---
        output = func(*args, **kwargs)

        # --- Create a unique filename for the persisted data ---
        module_name = inspect.getmodule(func).__name__
        func_name = func.__name__
        output_filename = os.path.join(OUTPUT_DIR, f"{module_name}.{func_name}.pkl")

        # --- Persist the arguments and the output ---
        with open(output_filename, "wb") as f:
            pickle.dump({
                "args": args,
                "kwargs": kwargs,
                "output": output
            }, f)

        # --- Return the original function's output ---
        return output

    return wrapper

def instrument_modules():
    """
    Finds and instruments all functions in modules with the specified prefix.
    """
    for module_name, module in sys.modules.items():
        if module_name.startswith(MODULE_PREFIX):
            for name, obj in inspect.getmembers(module):
                if inspect.isfunction(obj):
                    # --- Apply the decorator ---
                    setattr(module, name, persist_inputs_and_output(obj))

# --- Instrument the modules upon import ---
instrument_modules()