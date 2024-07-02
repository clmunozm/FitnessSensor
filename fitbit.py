import requests
from flask import Flask, request, redirect
import webbrowser
import os
import time
from threading import Thread, Event
from dotenv import load_dotenv
import tkinter as tk
from tkinter import messagebox
from datetime import date

# Cargar las variables de entorno desde el archivo .env
load_dotenv()

# Configuración de la aplicación Fitbit desde las variables de entorno
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
REDIRECT_URI = 'http://localhost:5000/bgames/fitness'
AUTHORIZATION_BASE_URL = 'https://www.fitbit.com/oauth2/authorize'
TOKEN_URL = 'https://api.fitbit.com/oauth2/token'
SCOPES = ['activity', 'nutrition', 'sleep', 'heartrate', 'weight', 'profile']

# Archivo para registrar las calorías procesadas
LOG_FILE = 'calories_log.txt'

app = Flask(__name__)
access_token = None
userID = None
capture_event = Event()

# Variable global para indicar el estado de autenticación de Fitbit
fitbit_authenticated = False

# Función para obtener el ID de usuario desde la API local
def get_user_id(username, password):
    try:
        response = requests.get(f"http://localhost:3010/player/{username}/{password}")
        if response.status_code == 200:
            return response.json()  # Asume que el servidor devuelve solo el userID
        else:
            messagebox.showerror("Authentication Error", "Invalid credentials or unable to reach the server.")
            return None
    except Exception as e:
        messagebox.showerror("Error", f"Failed to connect to the server: {e}")
        return None

# Ruta para iniciar el proceso de autorización
@app.route('/')
def login():
    auth_url = f"{AUTHORIZATION_BASE_URL}?response_type=code&client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&scope={' '.join(SCOPES)}"
    return redirect(auth_url)

# Ruta para manejar el callback de OAuth2.0
@app.route('/bgames/fitness')
def callback():
    global access_token, fitbit_authenticated
    code = request.args.get('code')
    token_response = requests.post(TOKEN_URL, data={
        'client_id': CLIENT_ID,
        'grant_type': 'authorization_code',
        'redirect_uri': REDIRECT_URI,
        'code': code,
    }, auth=(CLIENT_ID, CLIENT_SECRET)).json()
    
    if 'access_token' in token_response:
        access_token = token_response['access_token']
        
        # Guardar el token en una variable de entorno para la demostración
        os.environ['FITBIT_ACCESS_TOKEN'] = access_token
        
        # Indicar que la autenticación de Fitbit fue exitosa
        fitbit_authenticated = True
    else:
        error_message = token_response.get('errors', [{'message': 'Unknown error'}])[0]['message']
        messagebox.showerror("Authentication Error", f"Failed to authenticate with Fitbit: {error_message}")
    
    return "Authentication process completed. You can close this window."

# Función para obtener datos de Fitbit
def get_fitbit_data(endpoint):
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    response = requests.get(f'https://api.fitbit.com/1/user/-/{endpoint}.json', headers=headers)
    return response.json()

# Función para leer el registro de calorías procesadas
def read_calories_log():
    if not os.path.exists(LOG_FILE):
        return None, 0  # Si el archivo no existe, no hay datos previos
    with open(LOG_FILE, 'r') as file:
        try:
            data = file.readlines()
            last_entry = data[-1].strip().split(',')
            last_date = last_entry[0]
            last_calories = int(last_entry[1])
            return last_date, last_calories
        except (ValueError, IndexError):
            return None, 0  # Si el archivo está vacío o no contiene un formato válido

# Función para escribir en el registro de calorías procesadas
def write_calories_log(date, calories):
    with open(LOG_FILE, 'a') as file:
        file.write(f"{date},{calories}\n")

# Función para calcular puntos y registrar calorías procesadas
def calculate_points_and_update_log(calories_out):
    today = date.today().isoformat()
    last_date, last_calories = read_calories_log()
    
    if last_date != today:
        # Es un nuevo día, calcular puntos y actualizar el registro
        points = calories_out // 100  # 1 punto por cada 100 calorías
        write_calories_log(today, calories_out)
        return points
    else:
        # Ya se han registrado las calorías para hoy
        return 0

# Función para capturar datos periódicamente
def capture_data_periodically():
    while not capture_event.is_set():
        if access_token:
            # Obtener datos de actividad del día actual
            activity_data = get_fitbit_data('activities/date/today')
            print("Activity Data:")
            print(activity_data)
            
            # Verificar si el token de acceso sigue siendo válido
            if 'errors' in activity_data and activity_data['errors'][0]['errorType'] == 'invalid_token':
                messagebox.showerror("Token Error", "Fitbit access token expired or invalid. Please authenticate again.")
                stop_capture()
                return
            
            # Extraer calorías quemadas del resumen de datos de actividad
            calories_out = activity_data['summary']['caloriesOut']
            print(f"Calories Out: {calories_out}")
            
            # Calcular puntos y actualizar el registro de calorías procesadas
            points = calculate_points_and_update_log(calories_out)
            print(f"Points earned: {points}")
        
        # Esperar 15 minutos antes de la próxima captura
        capture_event.wait(900)

# Interfaz gráfica
def start_gui():
    def authenticate():
        username = username_entry.get()
        password = password_entry.get()
        global userID
        userID = get_user_id(username, password)
        if userID:
            #messagebox.showinfo("Success", f"User ID obtained: {userID}")
            username_label.pack_forget()
            username_entry.pack_forget()
            password_label.pack_forget()
            password_entry.pack_forget()
            authenticate_button.pack_forget()
            start_button.config(state=tk.NORMAL)
        else:
            messagebox.showerror("Authentication Error", "Failed to obtain User ID.")
    
    def start_capture():
        # Abrir el navegador para iniciar el proceso de autenticación de Fitbit
        webbrowser.open('http://localhost:5000/')
        start_button.config(state=tk.DISABLED)
        capture_label.config(text="Please complete Fitbit authentication in the browser...")

    def stop_capture():
        capture_event.set()
        start_button.config(text="Start Capture", command=start_capture, state=tk.NORMAL)
        capture_label.config(text="Capture stopped.")

    def check_fitbit_authentication():
        if fitbit_authenticated:
            capture_label.config(text="Capturing Fitbit data...")
            start_button.config(text="Stop Capture", command=stop_capture, state=tk.NORMAL)
            # Iniciar la captura de datos
            capture_event.clear()
            capture_thread = Thread(target=capture_data_periodically)
            capture_thread.start()
        else:
            # Volver a verificar después de un corto período de tiempo
            root.after(1000, check_fitbit_authentication)

    def on_closing():
        capture_event.set()
        root.destroy()
        os._exit(0)

    root = tk.Tk()
    root.title("Fitness Data Capture")

    # Aumentar el tamaño de la ventana
    window_width = 400
    window_height = 300
    root.geometry(f"{window_width}x{window_height}")

    # Centrar la ventana en la pantalla
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    position_top = int((screen_height - window_height) / 2)
    position_right = int((screen_width - window_width) / 2)
    root.geometry(f"+{position_right}+{position_top}")

    username_label = tk.Label(root, text="Username:")
    username_label.pack()
    username_entry = tk.Entry(root)
    username_entry.pack()
    
    password_label = tk.Label(root, text="Password:")
    password_label.pack()
    password_entry = tk.Entry(root, show='*')
    password_entry.pack()
    
    authenticate_button = tk.Button(root, text="Authenticate", command=authenticate)
    authenticate_button.pack()

    capture_label = tk.Label(root, text="")
    capture_label.pack()

    start_button = tk.Button(root, text="Start Capture", state=tk.DISABLED, command=start_capture)
    start_button.pack()

    root.protocol("WM_DELETE_WINDOW", on_closing)  # Manejo del cierre de ventana

    # Verificar continuamente si la autenticación con Fitbit ha sido exitosa
    check_fitbit_authentication()

    root.mainloop()

if __name__ == '__main__':
    # Iniciar la aplicación Flask en un hilo separado
    server = Thread(target=app.run, kwargs={'debug': False, 'use_reloader': False})
    server.start()

    # Iniciar la interfaz gráfica
    start_gui()
