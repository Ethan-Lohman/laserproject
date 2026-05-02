# ========================================================================================
# IMPORTS AND DEPENDENCIES
# ========================================================================================
from tkinter import *
from PIL import Image, ImageTk
from tkinter import messagebox
import json
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import threading
import cv2
import numpy as np
import os
import queue
import subprocess
import time
import init  # for PASSWORDS /IMG FILE PATH 


# ========================================================================================
# CONSTANTS AND CONFIGURATION
# ========================================================================================
PASSWORD = init.IMG_PASSWORD  # password for uploading images
DELETE_PASSWORD = init.DEL_IMG_PASSWORD  # password for deleting images
ADMIN_PASSWORD = init.ADMIN_PASSWORD  # password for admin locking
IMG_PATH = init.TRACK_DIR  # directory for storing images

# Paths and directories
script_dir = os.path.dirname(os.path.abspath(__file__))
LOCK_FILE = os.path.join(script_dir, "lock.txt")
tracks_dir = os.path.join(IMG_PATH, 'img')
keystone_config_file = os.path.join(script_dir, "keystone_config.json")
scale_config_file = os.path.join(script_dir, "scale_config.json")
PROJECTOR_STATE_FILE = os.path.join(script_dir, "projector_state.txt")


# ========================================================================================
# GLOBAL VARIABLES
# ========================================================================================
# Tk root window
master = Tk()
master.title("Image Projector")
master.geometry("800x1000")
master.attributes('-fullscreen', True)


# Image and track management
track_files = []
imgPaths = {}
selected_image = StringVar()

# Scale and keystone configuration
scale = IntVar(value=100)
keystone_points = {}
scale_points = {}

# UI thread queue and button tracking
tk_queue = queue.Queue()
buttons = []

# Flask app initialization
app = Flask(__name__)
CORS(app)


# ========================================================================================
# UTILITY: Load image paths from directory
# ========================================================================================
def _load_track_files():
    """Load available track files from the images directory."""
    global track_files, imgPaths
    track_files = []
    imgPaths = {}
    
    if os.path.isdir(tracks_dir):
        for fname in sorted(os.listdir(tracks_dir)):
            if fname.lower().endswith(('.png', '.jpg', '.jpeg')):
                track_files.append(os.path.join(tracks_dir, fname))
    
    for i, path in enumerate(track_files, 1):
        imgPaths[f'option{i}'] = path

_load_track_files()



# ========================================================================================
# CONFIGURATION MANAGEMENT: Scale and Keystone
# ========================================================================================
def load_scale_config():
    """Load per-image scale mappings or a legacy single-scale format."""
    global scale_points
    try:
        if os.path.exists(scale_config_file):
            with open(scale_config_file, 'r') as f:
                data = json.load(f)
                # support legacy format {"scale": 120}
                if isinstance(data, dict) and 'scale' in data and len(data) == 1:
                    scale_points = {'__default__': int(data['scale'])}
                elif isinstance(data, dict):
                    # assume keys are image paths or '__default__'
                    scale_points = {k: int(v) for k, v in data.items()}
    except Exception as e:
        print(f"Failed to load scale config: {e}")


def save_scale_config():
    """Save scale configuration to file."""
    try:
        with open(scale_config_file, 'w') as f:
            json.dump(scale_points, f, indent=2)
        print(f"Scale saved to {scale_config_file}")
    except Exception as e:
        print(f"Failed to save scale config: {e}")


def get_saved_scale_for_image(image_path):
    """Get the saved scale for a specific image or return default."""
    if image_path in scale_points:
        return int(scale_points[image_path])
    if '__default__' in scale_points:
        return int(scale_points['__default__'])
    return int(scale.get())


def load_keystone_config():
    """Load keystone point configuration from file."""
    global keystone_points
    try:
        if os.path.exists(keystone_config_file):
            with open(keystone_config_file, 'r') as f:
                keystone_points = json.load(f)
    except Exception as e:
        print(f"Failed to load keystone config: {e}")


def save_keystone_config():
    """Save keystone point configuration to file."""
    try:
        with open(keystone_config_file, 'w') as f:
            json.dump(keystone_points, f, indent=2)
        print(f"Keystone saved to {keystone_config_file}")
    except Exception as e:
        print(f"Failed to save keystone config: {e}")


# ========================================================================================
# SECURITY: Lock/Admin Functions
# ========================================================================================
def is_locked(password=None):
    """Check if the system is locked. Admin password unlocks the check."""
    if password == ADMIN_PASSWORD:
        return False
    return os.path.exists(LOCK_FILE)


# ========================================================================================
# UI THREAD MANAGEMENT: Queue Processing
# ========================================================================================
def process_tk_queue():
    """Process queued UI tasks from Flask threads."""
    try:
        while True:
            task = tk_queue.get_nowait()
            task()
    except queue.Empty:
        pass
    master.after(10, process_tk_queue)

master.after(10, process_tk_queue)



# ========================================================================================
# FLASK API: Image Projection Control
# ========================================================================================
@app.route('/projectCertainImage', methods=['POST'])
def projectCertainImage():
    """Project a specific image in fullscreen with saved scale."""
    data = request.get_json()
    admin_pass = data.get('admin_password')
    if is_locked(admin_pass):
        return jsonify({'error': 'System is locked'}), 403
    
    if 'selected' not in data:
        return jsonify({'error': 'Missing selectted image'}), 400
    
    selected = data['selected']
    
    if selected not in imgPaths:
        return jsonify({'error': 'Invalid selected image'}), 400
    
    path = imgPaths[selected]
    
    pressEscape()
    selected_image.set(imgPaths[selected])
    tk_queue.put(lambda: select_track(path))
    saved_scale = get_saved_scale_for_image(path)
    tk_queue.put(lambda: scale.set(saved_scale))
    tk_queue.put(project_fullscreen)
    
    return jsonify({'message': f'Projecting {selected} with scale {saved_scale}%.'})


@app.route('/getState', methods=['GET'])
def getState():
    """Get current projection state including dimensions and scale."""
    try:
        img_path = selected_image.get()
        img = Image.open(img_path)
        iw, ih = img.size
        sw, sh = master.winfo_screenwidth(), master.winfo_screenheight()
        
        saved_scale = get_saved_scale_for_image(img_path)
        r = min(sw / iw, sh / ih) * (scale.get() / 100)
        w, h = int(iw * r), int(ih * r)
        return jsonify({'scale': saved_scale, 'width': w, 'height': h})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

#=======================================================================================
# FLASK API: System Control (Reboot)
#=======================================================================================

@app.route('/reboot', methods=['POST'])
def reboot():
    subprocess.Popen(['sudo', 'reboot', 'now'])
    return jsonify({'message': 'System rebooting...'})



# ========================================================================================
# FLASK API: Scale Control
# ========================================================================================
@app.route('/setScale', methods=['POST'])
def setScale():
    """Set the projection scale percentage."""
    data = request.get_json()
    admin_pass = data.get('admin_password')
    if is_locked(admin_pass):
        return jsonify({'error': 'System is locked'}), 403
    
    if 'scale' in data:
        new_scale = int(data['scale'])
        if 10 <= new_scale <= 200:
            tk_queue.put(lambda: scale.set(new_scale))
            current_image = selected_image.get()
            scale_points[current_image] = new_scale
            save_scale_config()
            return jsonify({'message': f'Scale queued to {new_scale}%'})
    return jsonify({'error': 'Invalid scale'}), 400


# ========================================================================================
# FLASK API: Keystone Correction
# ========================================================================================
@app.route('/getKeystone', methods=['GET'])
def getKeystone():
    """Get keystone points for a specific image."""
    option = request.args.get('option')
    if option not in imgPaths:
        return jsonify({'error': 'Invalid option'}), 400
    path = imgPaths[option]
    try:
        img = Image.open(path)
        iw, ih = img.size
        
        default_points = [[0, 0], [iw, 0], [iw, ih], [0, ih]]
        points = keystone_points.get(path, default_points)
        
        return jsonify({'points': points})
    except Exception as e:
        print(f"Error loading image for keystone: {e}")
        return jsonify({'points': [[0,0],[0,0],[0,0],[0,0,]]})


@app.route('/setKeystone', methods=['POST'])
def setKeystone():
    """Set keystone points for a specific image."""
    data = request.get_json()
    admin_pass = data.get('admin_password')

    if is_locked(admin_pass):
        return jsonify({'error': 'System is locked'}), 403
    
    option = data.get('option')
    new_points = data.get('points')
    if not option or not new_points or len(new_points) != 4:
        return jsonify({'error': 'Invalid data'}), 400
    path = imgPaths.get(option)
    if not path:
        return jsonify({'error': 'Invalid option'}), 400
    keystone_points[path] = new_points
    save_keystone_config()
    return jsonify({'message': 'Keystone points updated'})


# ========================================================================================
# FLASK API: Image Management (Upload/Delete)
# ========================================================================================
@app.route('/image/<option>', methods=['GET'])
def get_image(option):
    """Get an image file by its option key."""
    if option not in imgPaths:
        return jsonify({'error': 'Invalid option'}), 400
    path = imgPaths[option]
    return send_file(path, mimetype='image/jpeg')


@app.route('/upload', methods=['POST'])
def upload_image():
    """Upload a new image file."""
    admin_pass = request.form.get('admin_password')
    if is_locked(admin_pass):
        return jsonify({'error': 'System is locked'}), 403
    
    password = request.form.get('password')
    if password != PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    allowed_extensions = ('.png', '.jpg', '.jpeg')
    _, ext = os.path.splitext(file.filename.lower())
    if ext not in allowed_extensions:
        return jsonify({'error': 'Unsupported file type'}), 400
    
    file_name = file.filename
    dest_path = os.path.join(tracks_dir, file_name)
    file.save(dest_path)
    
    new_key = f'option{len(imgPaths) + 1}'
    imgPaths[new_key] = dest_path
    
    return jsonify({'message': 'File uploaded successfully', 'key': new_key, 'file_name': file_name}), 200


@app.route('/delete', methods=['POST'])
def delete_image():
    """Delete an image file."""
    admin_pass = request.form.get('admin_password')
    if is_locked(admin_pass):
        return jsonify({'error': 'System is locked'}), 403
    
    password = request.form.get('password')
    if password != DELETE_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    
    option = request.form.get('option')
    if not option:
        return jsonify({'error': 'No option specified'}), 400
    
    if option not in imgPaths:
        return jsonify({'error': 'Invalid option'}), 400
    
    # Get the file path
    file_path = imgPaths[option]
    
    # Remove from imgPaths
    del imgPaths[option]
    
    # Try to delete the file
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        print(f"Warning: Could not delete file {file_path}: {e}")
    
    # Renumber the remaining options
    new_imgPaths = {}
    for i, (key, path) in enumerate(sorted(imgPaths.items()), 1):
        new_imgPaths[f'option{i}'] = path
    imgPaths.clear()
    imgPaths.update(new_imgPaths)
    
    return jsonify({'message': 'Image deleted successfully'}), 200


@app.route('/options', methods=['GET'])
def get_options():
    """Get list of available image options."""
    options = []
    for key in sorted(imgPaths.keys()):
        path = imgPaths[key]
        filename = os.path.basename(path)
        label = filename.rsplit('.', 1)[0].replace('_', ' ').title()
        options.append({'value': key, 'label': label})
    return jsonify(options)


# ========================================================================================
# FLASK API: System Lock/Admin Control
# ========================================================================================
@app.route('/lock/status', methods=['GET'])
def lock_status():
    """Get the current lock status of the system."""
    return jsonify({'locked': is_locked()})


@app.route('/lock', methods=['POST'])
def lock_system():
    """Lock the system with admin password."""
    data = request.get_json()
    password = data.get('password')
    
    if password != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        with open(LOCK_FILE, 'w') as f:
            f.write(f"Locked at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        return jsonify({'message': 'System locked', 'locked': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/unlock', methods=['POST'])
def unlock_system():
    """Unlock the system with admin password."""
    data = request.get_json()
    password = data.get('password')
    
    if password != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
        return jsonify({'message': 'System unlocked', 'locked': False})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ========================================================================================
# FLASK API: Boundary Detection
# ========================================================================================
@app.route('/startBoundaryDetection', methods=['POST'])
def startBoundaryDetection():
    """Start the boundary detection subprocess."""
    subprocess.Popen(['python', 'boundaryDetection.py'])
    return jsonify({'message': 'Boundary detection started'})


@app.route('/stopBoundaryDetection', methods=['POST'])  
def stopBoundaryDetection():
    """Stop the boundary detection subprocess."""
    subprocess.Popen(['pkill', '-f', 'boundaryDetection.py'])
    return jsonify({'message': 'Boundary detection stopped'})


# ========================================================================================
# FLASK API: Press Escape (to close track projection)
# ========================================================================================
@app.route('/pressEscape', methods=['POST'])
def press_escape_endpoint():
    """Endpoint to simulate ESC key press to close fullscreen windows."""
    try:
        tk_queue.put(pressEscape)
        return jsonify({'message': 'Escape key press simulated'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
# ========================================================================================
# HELPER FUNCTIONS
# ========================================================================================
def pressEscape():
    """Helper function to simulate ESC key press to close any fullscreen windows."""
    for child in master.winfo_children():
        if isinstance(child, Toplevel) and child.winfo_exists() and child.attributes('-fullscreen'):
            child.event_generate('<Escape>')
            break


def run_flask():
    """Run Flask development server."""
    app.run(host='0.0.0.0', port=5000)


# ========================================================================================
# IMAGE PROJECTION AND DISPLAY
# ========================================================================================
def project_fullscreen():
    """Project the selected image in fullscreen with applied scale and keystone."""
    img = Image.open(selected_image.get())
    current_image = selected_image.get()
    sw, sh = master.winfo_screenwidth(), master.winfo_screenheight()
    iw, ih = img.size

    # Pillow resampling compatibility
    try:
        resample_lanczos = Image.Resampling.LANCZOS
    except Exception:
        resample_lanczos = Image.LANCZOS

    # First apply keystone transform if saved points exist
    if current_image in keystone_points:
        try:
            points = keystone_points[current_image]
            src = np.float32([[0,0],[iw,0],[iw,ih],[0,ih]])
            dst = np.float32(points)
            M = cv2.getPerspectiveTransform(src, dst)
            img_cv = cv2.cvtColor(np.array(img.convert('RGB')), cv2.COLOR_RGB2BGR)
            warped_cv = cv2.warpPerspective(img_cv, M, (iw, ih))
            warped_rgb = cv2.cvtColor(warped_cv, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(warped_rgb)
            iw, ih = img.size  # update size after keystone
        except Exception as e:
            print(f"Failed to apply keystone: {e}")

    # Then apply scaling to the (possibly keystoned) image
    r = min(sw / iw, sh / ih) * (scale.get() / 100)
    img = img.resize((int(iw * r), int(ih * r)), resample_lanczos)

    # Create and show the fullscreen window
    top = Toplevel(master)
    top.attributes('-fullscreen', True)
    top.configure(bg='black')
    photo = ImageTk.PhotoImage(img)

    Label(top, image=photo, bg='black').pack(expand=True)
    top.image = photo
    top.bind('<Escape>', lambda e: top.destroy())
    top.bind('<space>', lambda e: top.destroy())


def select_track(path):
    """Select a track and update UI state."""
    selected_image.set(path)
    for btn, img_path in buttons:
        if img_path == path:
            btn.config(bg='#4CAF50', relief=SUNKEN)
        else:
            btn.config(bg='lightgray', relief=RAISED)
    # Apply per-image saved scale (if any) when selecting a track
    try:
        saved = get_saved_scale_for_image(path)
        scale.set(int(saved))
    except Exception:
        pass
    #update_button_status()
    update_dimensions()


def update_dimensions(*args):
    """Update the projection dimensions label based on current image and scale."""
    try:
        img = Image.open(selected_image.get())
        sw, sh = master.winfo_screenwidth(), master.winfo_screenheight()
        iw, ih = img.size
        r = min(sw / iw, sh / ih) * (scale.get() / 100)
        w, h = int(iw * r), int(ih * r)
        #dim_label.config(text=f"Projection: {w} x {h} px")
    except:
        #dim_label.config(text="Image not found")
        print("Failed to update dimensions - image not found")





# ========================================================================================
# PROJECTOR CONTROL: Power Management
# ========================================================================================

def find_projector_device():
    """Scan CEC bus and return the best projector/display device number."""
    try:
        # Scan for CEC devices to find the projector
        scan_result = subprocess.run(
            'echo "scan" | cec-client -s -d 1',
            shell=True,
            capture_output=True,
            text=True,
            timeout=15
        )

        # Look for TV/device 0 or other display devices
        scan_output = scan_result.stdout.lower()
        target_device = None

        # Try device 0 (TV) first, then look for other display devices
        if "device #0" in scan_output and ("tv" in scan_output or "display" in scan_output):
            target_device = "0"
        else:
            # Look for other potential display devices
            for line in scan_output.split('\n'):
                if 'device #' in line and ('tv' in line.lower() or 'display' in line.lower() or 'projector' in line.lower()):
                    device_num = line.split('#')[1].split()[0]
                    target_device = device_num
                    break

        if not target_device:
            target_device = "0"  # Default fallback

        return target_device

    except Exception as e:
        print(f"Failed to scan CEC devices: {e}")
        return "0"  # Default fallback on error


def turn_projector_on():
    """Turn on the projector using CEC-client with device scanning."""
    try:
        target_device = find_projector_device()
        print(f"Targeting CEC device {target_device}")

        commands = [
            f'echo "on {target_device}" | cec-client -s -d 1',
            f'echo "standby {target_device}" | cec-client -s -d 1',
            f'echo "on {target_device}" | cec-client -s -d 1'
        ]

        for cmd in commands:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                time.sleep(2)
                status_result = subprocess.run(
                    f'echo "pow {target_device}" | cec-client -s -d 1',
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=5
                )

                if "power status: on" in status_result.stdout.lower():
                    print("Projector turned ON")
                    save_projector_state_on()
                    return True

        print("CEC command sent - assuming projector ON")
        save_projector_state_on()
        return True

    except subprocess.TimeoutExpired:
        print("CEC command timed out")
        return False
    except Exception as e:
        print(f"Failed to turn on projector: {e}")
        return False


def turn_projector_off():
    """Turn off the projector using CEC-client with device scanning."""
    try:
        target_device = find_projector_device()
        print(f"Targeting CEC device {target_device}")

        result = subprocess.run(
            f'echo "standby {target_device}" | cec-client -s -d 1',
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            time.sleep(2)
            status_result = subprocess.run(
                f'echo "pow {target_device}" | cec-client -s -d 1',
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )

            if "power status: standby" in status_result.stdout.lower():
                print("Projector turned OFF")
                save_projector_state_off()
                return True

        print("CEC command sent - assuming projector OFF")
        save_projector_state_off()
        return True

    except subprocess.TimeoutExpired:
        print("CEC command timed out")
        return False
    except Exception as e:
        print(f"Failed to turn off projector: {e}")
        return False


def toggle_projector():
    """Toggle the projector state via user dialog."""
    result = messagebox.askyesnocancel("Projector Control", "Yes: Turn On\nNo: Turn Off\nCancel: Do Nothing")
    if result is True:
        turn_projector_on()
    elif result is False:
        turn_projector_off()


def get_actual_projector_state():
    """Check projector state using xrandr (HDMI signal status)."""
    try:
        result = subprocess.run(['xrandr'], capture_output=True, text=True, check=True)
        # If HDMI-1 has a resolution (not just "disconnected"), it's ON
        for line in result.stdout.split('\n'):
            if line.startswith('HDMI-1'):
                # Example: "HDMI-1 connected primary 1920x1080+0+0..."
                # If it has coordinates like "+0+0", it's active
                if '+' in line and 'x' in line:
                    return True
        return False
    except Exception as e:
        print(f"Failed to check projector state: {e}")
        return False

def save_projector_state_on():
    """Create the projector state file to indicate ON."""
    try:
        with open(PROJECTOR_STATE_FILE, 'w') as f:
            f.write("on")
    except Exception as e:
        print(f"Failed to save projector state: {e}")


def save_projector_state_off():
    """Delete the projector state file to indicate OFF."""
    try:
        if os.path.exists(PROJECTOR_STATE_FILE):
            os.remove(PROJECTOR_STATE_FILE)
    except Exception as e:
        print(f"Failed to delete projector state: {e}")


def get_saved_projector_state():
    """Return 'on' if file exists, otherwise 'off'."""
    return "on" if os.path.exists(PROJECTOR_STATE_FILE) else "off"



# FLASK API: Projector Control
@app.route('/projector/on', methods=['POST'])
def projector_on_endpoint():
    """Endpoint to turn projector on."""
    data = request.get_json() if request.is_json else {}
    admin_pass = data.get('admin_password')
    if is_locked(admin_pass):
        return jsonify({'error': 'System is locked'}), 403
    
    try:
        tk_queue.put(turn_projector_on)
        return jsonify({'success': True, 'message': 'Projector turned ON'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/projector/off', methods=['POST'])
def projector_off_endpoint():
    """Endpoint to turn projector off."""
    data = request.get_json() if request.is_json else {}
    admin_pass = data.get('admin_password')
    if is_locked(admin_pass):
        return jsonify({'error': 'System is locked'}), 403
    
    try:
        tk_queue.put(turn_projector_off)
        return jsonify({'success': True, 'message': 'Projector turned OFF'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/projector/status', methods=['GET'])
def projector_status_endpoint():
    """Return the saved current projector state."""
    try:
        state = get_saved_projector_state()
        return jsonify({'on': state == 'on', 'state': state})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ========================================================================================
# FULLSCREEN CONTROL
# ========================================================================================
def escapeFullscreen():
    """Exit fullscreen mode."""
    master.attributes('-fullscreen', False)


def makeFullscreen():
    """Enter fullscreen mode."""
    master.attributes('-fullscreen', True)

# ========================================================================================
# KEYSTONE CALIBRATION
# ========================================================================================
def open_keystone_calibrator():
    """Opens the keystone calibrator window when the button is pressed.
    
    Allows users to drag corner points to correct keystone distortion with
    optional live preview of the projected image.
    """
    # Opens a Toplevel window with draggable corner points for the currently selected image
    try:
        original_img = Image.open(selected_image.get())
    except Exception as e:
        tk_popup = Toplevel(master)
        Label(tk_popup, text=f"Failed to open image:\n{e}", fg='red').pack(padx=20, pady=20)
        return

    iw, ih = original_img.size
    current_image = selected_image.get()
    # load saved points for this image if present
    if current_image in keystone_points:
        try:
            points = [list(p) for p in keystone_points[current_image]]
        except Exception:
            points = [[0, 0], [iw, 0], [iw, ih], [0, ih]]
    else:
        points = [[0, 0], [iw, 0], [iw, ih], [0, ih]]
    selected_point = None
    scale_factor = 0.5
    live_projection_enabled = BooleanVar(value=False)
    live_projection_window = None

    # resampling fallback
    try:
        resample_lanczos = Image.Resampling.LANCZOS
    except Exception:
        resample_lanczos = Image.LANCZOS

    cal = Toplevel(master)
    cal.title("Keystone Calibrator")

    info = Label(cal, text="Drag the corner points to correct keystone. Toggle live projection to see changes in real-time.")
    info.pack(pady=8)

    canvas = Canvas(cal, width=int(iw * scale_factor), height=int(ih * scale_factor), bg='black')
    canvas.pack()

    def create_live_projection_window():
        """Create the live projection window with draggable corner markers."""
        nonlocal live_projection_window
        if live_projection_window and live_projection_window.winfo_exists():
            return  # Window already exists
        
        live_projection_window = Toplevel(master)
        live_projection_window.attributes('-fullscreen', True)
        live_projection_window.attributes('-topmost', True)  # Keep on top
        live_projection_window.configure(bg='black')
        live_projection_window.title("Live Keystone Projection")
        
        # Use a canvas instead of label to allow drawing markers
        sw, sh = master.winfo_screenwidth(), master.winfo_screenheight()
        live_projection_window.canvas = Canvas(live_projection_window, width=sw, height=sh, 
                                               bg='black', highlightthickness=0)
        live_projection_window.canvas.pack(fill=BOTH, expand=True)
        
        # Store the selected point index for dragging
        live_projection_window.selected_marker = None
        
        # Add text overlay to show it's in live calibration mode
        info_label = Label(live_projection_window, text="Drag corner points to adjust keystone - Press ESC or SPACE to close", 
                          fg='yellow', bg='black', font=('Arial', 14, 'bold'))
        info_label.place(x=10, y=10)
        
        # Bind mouse events for dragging markers on the projection
        live_projection_window.canvas.bind('<ButtonPress-1>', on_projection_mouse_down)
        live_projection_window.canvas.bind('<B1-Motion>', on_projection_mouse_move)
        live_projection_window.canvas.bind('<ButtonRelease-1>', on_projection_mouse_up)
        
        # Bind escape key to close projection
        live_projection_window.bind('<Escape>', lambda e: close_live_projection())
        live_projection_window.bind('<space>', lambda e: close_live_projection())
        
        return live_projection_window

    def close_live_projection():
        """Close the live projection window."""
        nonlocal live_projection_window
        if live_projection_window and live_projection_window.winfo_exists():
            live_projection_window.destroy()
            live_projection_window = None

    def on_projection_mouse_down(event):
        """Handle mouse down on projection window to select a corner marker."""
        if not live_projection_window or not hasattr(live_projection_window, 'marker_positions'):
            return
        
        # Check if clicked near any marker
        for i, (mx, my) in enumerate(live_projection_window.marker_positions):
            distance = ((event.x - mx) ** 2 + (event.y - my) ** 2) ** 0.5
            if distance < 30:  # 30 pixel radius for selection
                live_projection_window.selected_marker = i
                break

    def on_projection_mouse_move(event):
        """Handle mouse move on projection window to drag corner markers."""
        if not live_projection_window or live_projection_window.selected_marker is None:
            return
        
        # Get screen dimensions
        sw, sh = master.winfo_screenwidth(), master.winfo_screenheight()
        
        # Calculate the offset and scale of the projected image
        current_scale = scale.get() / 100
        r = min(sw / iw, sh / ih) * current_scale
        proj_w, proj_h = int(iw * r), int(ih * r)
        offset_x = (sw - proj_w) // 2
        offset_y = (sh - proj_h) // 2
        
        # Convert screen coordinates to image coordinates
        img_x = (event.x - offset_x) / r
        img_y = (event.y - offset_y) / r
        
        # Clamp to image bounds
        img_x = max(0, min(iw, img_x))
        img_y = max(0, min(ih, img_y))
        
        # Update the keystone point
        points[live_projection_window.selected_marker] = [img_x, img_y]
        
        # Update both preview and projection
        draw_preview_local()

    def on_projection_mouse_up(event):
        """Handle mouse up on projection window to deselect marker."""
        if live_projection_window:
            live_projection_window.selected_marker = None

    def update_live_projection():
        """Update the live projection with current keystone points and draw corner markers."""
        if not live_projection_enabled.get() or not live_projection_window or not live_projection_window.winfo_exists():
            return
        
        try:
            # Get screen dimensions
            sw, sh = master.winfo_screenwidth(), master.winfo_screenheight()
            
            # Apply keystone transform
            src = np.float32([[0,0],[iw,0],[iw,ih],[0,ih]])
            dst = np.float32(points)
            M = cv2.getPerspectiveTransform(src, dst)
            img_cv = cv2.cvtColor(np.array(original_img.convert('RGB')), cv2.COLOR_RGB2BGR)
            warped_cv = cv2.warpPerspective(img_cv, M, (iw, ih))
            warped_rgb = cv2.cvtColor(warped_cv, cv2.COLOR_BGR2RGB)
            transformed_img = Image.fromarray(warped_rgb)
            
            # Apply scaling
            current_scale = scale.get() / 100
            r = min(sw / iw, sh / ih) * current_scale
            proj_w, proj_h = int(iw * r), int(ih * r)
            final_img = transformed_img.resize((proj_w, proj_h), resample_lanczos)
            
            # Clear canvas
            live_projection_window.canvas.delete('all')
            
            # Calculate centering offset
            offset_x = (sw - proj_w) // 2
            offset_y = (sh - proj_h) // 2
            
            # Draw the image on canvas
            photo = ImageTk.PhotoImage(final_img)
            live_projection_window.canvas.create_image(offset_x, offset_y, anchor=NW, image=photo)
            live_projection_window.canvas.image = photo  # Keep a reference
            
            # Draw corner markers at keystone point positions
            marker_positions = []
            marker_colors = ['red', 'green', 'blue', 'yellow']
            marker_labels = ['Top-Left', 'Top-Right', 'Bottom-Right', 'Bottom-Left']
            
            for i, (px, py) in enumerate(points):
                # Convert image coordinates to screen coordinates
                screen_x = offset_x + px * r
                screen_y = offset_y + py * r
                marker_positions.append((screen_x, screen_y))
                
                # Draw marker circle (larger if currently selected)
                is_selected = (hasattr(live_projection_window, 'selected_marker') and 
                              live_projection_window.selected_marker == i)
                marker_radius = 20 if is_selected else 15
                outline_width = 5 if is_selected else 3
                color = marker_colors[i]
                
                live_projection_window.canvas.create_oval(
                    screen_x - marker_radius, screen_y - marker_radius,
                    screen_x + marker_radius, screen_y + marker_radius,
                    fill=color, outline='white', width=outline_width, tags='marker'
                )
                
                # Draw label
                live_projection_window.canvas.create_text(
                    screen_x, screen_y - 30 if is_selected else screen_y - 25,
                    text=marker_labels[i], fill='white', 
                    font=('Arial', 12 if is_selected else 10, 'bold'), tags='marker'
                )
            
            # Store marker positions for hit detection
            live_projection_window.marker_positions = marker_positions
            
            # Draw connecting lines between corners to show the projection boundaries
            if len(marker_positions) == 4:
                # Draw lines connecting the corners
                for i in range(4):
                    x1, y1 = marker_positions[i]
                    x2, y2 = marker_positions[(i + 1) % 4]
                    live_projection_window.canvas.create_line(
                        x1, y1, x2, y2,
                        fill='cyan', width=2, dash=(5, 5), tags='marker'
                    )
            
        except Exception as e:
            print(f"Failed to update live projection: {e}")

    def toggle_live_projection():
        """Toggle the live projection window on/off."""
        if live_projection_enabled.get():
            create_live_projection_window()
            update_live_projection()
        else:
            close_live_projection()

    def draw_preview_local():
        canvas.delete('all')
        img_resized = original_img.resize((int(iw * scale_factor), int(ih * scale_factor)), resample_lanczos)
        preview_pil = img_resized.convert('RGB')
        marker = Image.new('RGBA', preview_pil.size)
        mpx = marker.load()
        for (x, y) in points:
            px, py = int(x * scale_factor), int(y * scale_factor)
            rr = 6
            for dx in range(-rr, rr+1):
                for dy in range(-rr, rr+1):
                    if dx*dx + dy*dy <= rr*rr:
                        mx, my = px+dx, py+dy
                        if 0 <= mx < marker.size[0] and 0 <= my < marker.size[1]:
                            mpx[mx, my] = (255, 0, 0, 255)
        preview = Image.alpha_composite(preview_pil.convert('RGBA'), marker)
        preview_tk = ImageTk.PhotoImage(preview.convert('RGB'))
        canvas.preview_img = preview_tk
        canvas.create_image(0, 0, anchor=NW, image=preview_tk)
        
        # Update live projection if enabled
        update_live_projection()

    def on_mouse_down(event):
        nonlocal selected_point
        x, y = event.x / scale_factor, event.y / scale_factor
        for i, (px, py) in enumerate(points):
            if abs(px - x) < 20 and abs(py - y) < 20:
                selected_point = i
                break

    def on_mouse_move(event):
        nonlocal selected_point
        if selected_point is not None:
            nx = max(0, min(iw, event.x / scale_factor))
            ny = max(0, min(ih, event.y / scale_factor))
            points[selected_point] = [nx, ny]
            draw_preview_local()

    def on_mouse_up(event):
        nonlocal selected_point
        selected_point = None

    canvas.bind('<ButtonPress-1>', on_mouse_down)
    canvas.bind('<B1-Motion>', on_mouse_move)
    canvas.bind('<ButtonRelease-1>', on_mouse_up)

    draw_preview_local()

    # Live projection toggle
    live_frame = Frame(cal)
    live_frame.pack(pady=10)
    live_checkbox = Checkbutton(live_frame, text="Enable Live Projection", 
                               variable=live_projection_enabled, 
                               command=toggle_live_projection,
                               font=('Arial', 11))
    live_checkbox.pack()

    # Scale adjustment for live preview
    scale_frame = Frame(cal)
    scale_frame.pack(pady=10)
    Label(scale_frame, text="Live Scale Adjustment:", font=('Arial', 10)).pack()
    
    live_scale = IntVar(value=scale.get())
    scale_slider = Scale(scale_frame, from_=10, to=200, orient=HORIZONTAL, 
                        variable=live_scale, length=300,
                        command=lambda v: update_live_scale())
    scale_slider.pack()
    
    def update_live_scale():
        """Update the main scale and refresh live projection."""
        scale.set(live_scale.get())
        update_live_projection()

    # Save / Reset / Close buttons
    def save_current_keystone():
        keystone_points[current_image] = [list(p) for p in points]
        save_keystone_config()
        messagebox.showinfo("Keystone Saved", f"Keystone saved for:\n{os.path.basename(current_image)}")

    def reset_keystone():
        nonlocal points
        points = [[0, 0], [iw, 0], [iw, ih], [0, ih]]
        draw_preview_local()

    def close_calibrator():
        close_live_projection()  # Close live projection if open
        cal.destroy()

    button_frame = Frame(cal)
    button_frame.pack(pady=10)
    Button(button_frame, text='Save Keystone', command=save_current_keystone, 
        bg='#4CAF50', fg='white', font=('Arial', 12)).pack(side=LEFT, padx=5)
    Button(button_frame, text='Reset', command=reset_keystone, 
        bg='#FF9800', fg='white', font=('Arial', 12)).pack(side=LEFT, padx=5)
    Button(button_frame, text='Close', command=close_calibrator, font=('Arial', 12)).pack(side=LEFT, padx=5)
    
    # Also bind window close event to cleanup
    cal.protocol("WM_DELETE_WINDOW", close_calibrator)


# ========================================================================================
# SCALE CALIBRATION
# ========================================================================================
def open_scale_calibrator():
    """Open a popup to adjust and save the projection scale."""
    cal = Toplevel(master)
    cal.title("Scale Calibrator")
    current_image = selected_image.get()
    # prefill with per-image saved value if present
    temp_scale = IntVar(value=get_saved_scale_for_image(current_image))

    Label(cal, text="Adjust scale (10-200)", font=("Arial", 12, "bold")).pack(pady=(10,5))
    s = Scale(cal, from_=10, to=200, orient=HORIZONTAL, variable=temp_scale, length=400)
    s.pack(padx=10, pady=5)

    preview = Label(cal, text=f"Scale: {temp_scale.get()}%", font=("Arial", 11))
    preview.pack(pady=5)

    def _on_temp_change(*args):
        preview.config(text=f"Scale: {temp_scale.get()}%")

    temp_scale.trace('w', _on_temp_change)

    def _save():
        scale.set(int(temp_scale.get()))
        # persist per-image scale
        try:
            scale_points[current_image] = int(temp_scale.get())
            save_scale_config()
        except Exception:
            pass
        messagebox.showinfo("Scale Saved", f"Scale saved: {temp_scale.get()}% for {os.path.basename(current_image)}")
        cal.destroy()

    def _cancel():
        cal.destroy()

    btn_frame = Frame(cal)
    btn_frame.pack(pady=10)
    Button(btn_frame, text='Save', command=_save, bg='#4CAF50', fg='white', font=('Arial', 12)).pack(side=LEFT, padx=5)
    Button(btn_frame, text='Cancel', command=_cancel, font=('Arial', 12)).pack(side=LEFT, padx=5)


master.configure(bg='black') #makes the background black - with no tkinter GUI elements 


# ========================================================================================
# FINAL INITIALIZATION AND MAIN LOOP
# ========================================================================================
# Start Flask API server
flask_thread = threading.Thread(target=run_flask)
flask_thread.daemon = True
flask_thread.start()
# Load any saved keystone configurations
load_keystone_config()
# Load saved scale (if any)
load_scale_config()

update_dimensions()

master.mainloop()