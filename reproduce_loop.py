import re
import signal
import time

def handler(signum, frame):
    raise TimeoutError("Timed out!")

signal.signal(signal.SIGALRM, handler)

def test_infinite_loop(text):
    print(f"Testing text: '{text}'")
    original_text = text
    try:
        signal.alarm(2)  # Set 2 second timeout
        start_time = time.time()
        
        # The logic from the script
        proj_municipality = text
        proj_municipality = re.sub(r'\s*\([^)]+\)\s*', ' ', proj_municipality)
        iterations = 0
        while '(' in proj_municipality:
            iterations += 1
            if iterations % 1000 == 0:
                print(f"  Iteration {iterations}...")
            
            prev = proj_municipality
            proj_municipality = re.sub(r'\s*\([^)]+\)\s*', ' ', proj_municipality)
            
            if prev == proj_municipality:
                print("  Stuck! String is not changing but '(' is still present.")
                break
                
        print(f"Finished in {time.time() - start_time:.4f}s. Result: '{proj_municipality}'")
        
    except TimeoutError:
        print("  Caught infinite loop! (Timeout)")
    finally:
        signal.alarm(0)

# Test cases
test_infinite_loop("Municipality (Region)")  # Normal case
test_infinite_loop("Municipality (Region")   # Malformed case (missing closing paren)
test_infinite_loop("Municipality (Region) (Province)") # Multiple parens
test_infinite_loop("Municipality (Region (Province)") # Nested/Malformed
