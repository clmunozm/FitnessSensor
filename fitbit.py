import requests
from flask import Flask, request, redirect
import webbrowser
import os
import time
from threading import Thread, Event
from dotenv import load_dotenv
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import PhotoImage
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

# Configuración de la URL de puntos
POINTS_URL = 'http://localhost:3002/adquired_subattribute/'
SENSOR_ENDPOINT_ID = '6'

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
        messagebox.showerror("Error", f"Failed to connect to the server")
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

    if 'errors' in token_response:
        error_message = token_response['errors'][0]['message']
        messagebox.showerror("Authentication Error", f"Failed to authenticate with Fitbit: {error_message}")
        return "Authentication failed. Please try again."
    
    return "Authentication process completed. You can close this window."

# Función para obtener datos de Fitbit
def get_fitbit_data(endpoint):
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    response = requests.get(f'https://api.fitbit.com/1/user/-/{endpoint}.json', headers=headers)
    return response.json()

# Función para leer el registro de calorías procesadas
def read_calories_log(user_id):
    if not os.path.exists(LOG_FILE):
        return None, 0  # Si el archivo no existe, no hay datos previos
    with open(LOG_FILE, 'r') as file:
        try:
            for line in file:
                date_entry, stored_user_id, calories = line.strip().split(',')
                if stored_user_id == str(user_id):
                    return date_entry, int(calories)
            return None, 0  # Si no se encuentra el usuario, devuelve valores predeterminados
        except (ValueError, IndexError):
            return None, 0  # Si el archivo está vacío o no contiene un formato válido

# Función para escribir en el registro de calorías procesadas
def write_calories_log(date, user_id, calories):
    updated = False
    lines = []
    
    # Leer todas las líneas del archivo
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as file:
            lines = file.readlines()
    
    # Revisar si ya existe una entrada para el usuario y la fecha actual
    with open(LOG_FILE, 'w') as file:
        for line in lines:
            stored_date, stored_user_id, stored_calories = line.strip().split(',')
            if stored_date == date and stored_user_id == str(user_id):
                # Actualizar las calorías si coincide la fecha y el ID de usuario
                file.write(f"{date},{user_id},{calories}\n")
                updated = True
            else:
                file.write(line)
        
        # Si no se encontró una entrada para la fecha y usuario, agregarla
        if not updated:
            file.write(f"{date},{user_id},{calories}\n")

# Función para calcular puntos y registrar calorías procesadas
def calculate_points_and_update_log(calories_out):
    global userID
    today = date.today().isoformat()
    last_date, last_calories = read_calories_log(userID)
    
    if last_date == today:
        # Es el mismo día, calcular puntos para calorías adicionales
        additional_calories = calories_out - last_calories
        if additional_calories > 0:
            points = additional_calories // 100 # 1 punto por cada 100 calorías adicionales
            updated_calories = last_calories + additional_calories
            # Enviar los puntos obtenidos a la API
            send_points_to_server(points)
            write_calories_log(today, userID, updated_calories) # Actualizar el log con las calorías acumuladas
            return points
        else:
            return 0
    else:
        # Es un nuevo día, calcular puntos para todas las calorías y reiniciar el log
        points = calories_out // 100
        # Enviar los puntos obtenidos a la API
        send_points_to_server(points)
        write_calories_log(today, userID, calories_out) # 1 punto por cada 100 calorías
        return points

# Función para enviar los puntos obtenidos a la API
def send_points_to_server(points):
    if points > 0:  # Solo enviar si se han obtenido puntos
        data = {
            "id_player": userID,
            "id_subattributes_conversion_sensor_endpoint": SENSOR_ENDPOINT_ID,
            "new_data": [str(points)]
        }
        try:
            response = requests.post(POINTS_URL, json=data)
            if response.status_code != 200:
                messagebox.showerror("Error", f"Error sending points, status code: {response.status_code}")
                os._exit(0)  # Asegurarse de que todos los hilos se cierren
    
        except Exception as e:
            messagebox.showerror("Error", f"Error sending points: {str(e)}")
            os._exit(0)  # Asegurarse de que todos los hilos se cierren
    

# Función para iniciar la interfaz gráfica
def start_gui():
    def authenticate():
        username = username_entry.get().strip()
        password = password_entry.get().strip()
        if not username or not password:
            messagebox.showwarning("Input Error", "Username and Password cannot be empty.")
            return
        global userID
        userID = get_user_id(username, password)
        if userID:
            login_frame.pack_forget()
            capture_frame.pack(fill="both", expand=True)
            start_button.config(state=tk.NORMAL)
    
    def start_capture():
        webbrowser.open('http://localhost:5000/')
        start_button.config(state=tk.DISABLED)
        capture_label.config(text="Please complete Fitbit authentication in the browser...")

    def stop_capture():
        capture_event.set()
        start_button.config(text="Start Capture", command=start_capture, state=tk.NORMAL)
        capture_label.config(text="Capture stopped.")
    
    def update_capture_data(calories_out, points, new_calories):
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        title_label.config(text=f"Last time updated: {current_time}")
        capture_label.config(text=f"Calories: {calories_out}\nNew Calories: {new_calories}\nPoints: {points}", font=('Helvetica', 14, 'bold'))

    def check_fitbit_authentication():
        if fitbit_authenticated:
            title_label.pack(pady=10)  # Muestra el título cuando la captura comienza
            capture_label.config(text="Capturing Fitbit data...")
            start_button.pack_forget()  # Elimina el botón de captura
            # Iniciar la captura de datos
            capture_event.clear()
            capture_thread = Thread(target=capture_data_periodically)
            capture_thread.start()
        else:
            # Volver a verificar después de un corto período de tiempo
            root.after(1000, check_fitbit_authentication)
    
    def capture_data_periodically():
        global userID
        while not capture_event.is_set():
            if access_token:
                # Obtener la fecha actual en formato YYYY-MM-DD
                current_date = date.today().isoformat()
                # Obtener datos de actividad de la fecha actual
                activity_data = get_fitbit_data(f'activities/date/{current_date}')
                
                # Verificar si el token de acceso sigue siendo válido
                if 'errors' in activity_data and activity_data['errors'][0]['errorType'] == 'invalid_token':
                    messagebox.showinfo("Reauthentication Required", "Reauthenticating with Fitbit...")
                    webbrowser.open('http://localhost:5000/')
                
                # Extraer calorías quemadas del resumen de datos de actividad
                calories_out = activity_data['summary']['caloriesOut']
                
                # Calcular nuevas calorías desde la última captura
                last_date, last_calories = read_calories_log(userID)
                if last_date == date.today().isoformat():
                    new_calories = calories_out - last_calories
                else:
                    new_calories = calories_out  # Todas las calorías son nuevas si es un día nuevo
                
                # Calcular puntos y actualizar el registro de calorías procesadas
                points = calculate_points_and_update_log(calories_out)
                
                # Actualizar la interfaz con los datos capturados
                update_capture_data(calories_out, points, new_calories)
            
            # Esperar 15 minutos antes de la próxima captura
            capture_event.wait(900)
    
    def on_closing():
        if messagebox.askokcancel("Quit", "Do you want to quit?"):
            root.destroy()
            os._exit(0)  # Asegurarse de que todos los hilos se cierren
    
    root = tk.Tk()
    root.title("Fitbit Data Capture")

    # Cambiar el color de fondo del root
    root.configure(bg='#f0f0f0')  # Fondo oscuro
    # Agregar ícono
    icon_image = PhotoImage(file='icon.png')  # Usa la ruta a tu icono
    root.iconphoto(True, icon_image)

    # Configuración de estilos personalizados
    style = ttk.Style()
    style.theme_use("clam")  # Elegante y minimalista

    # Cambiar estilos de los botones y etiquetas
    style.configure("TFrame", background="#f0f0f0")  # Aplica un color de fondo a los frames
    style.configure("TLabel", background="#f0f0f0", font=("Helvetica", 12))  # Asegúrate de que el fondo de las etiquetas coincida
    style.configure("TButton", background="#007BFF", foreground="#ffffff", font=("Helvetica", 12))  # Cambiar el color de los botones

    window_width, window_height = 500, 300
    screen_width, screen_height = root.winfo_screenwidth(), root.winfo_screenheight()
    position_top = int(screen_height / 2 - window_height / 2)
    position_right = int(screen_width / 2 - window_width / 2)
    root.geometry(f'{window_width}x{window_height}+{position_right}+{position_top}')

    # Frame de login
    login_frame = ttk.Frame(root, padding=20)
    login_frame.pack(fill="both", expand=True)
    login_frame.configure(style="TFrame")  # Aplica estilo al Frame
    
    ttk.Label(login_frame, text="Username:").pack(pady=5)
    username_entry = ttk.Entry(login_frame, width=30)
    username_entry.pack(pady=5)

    ttk.Label(login_frame, text="Password:").pack(pady=5)
    password_entry = ttk.Entry(login_frame, show="*", width=30)
    password_entry.pack(pady=5)

    authenticate_button = ttk.Button(login_frame, text="Authenticate", command=authenticate)
    authenticate_button.pack(pady=10)

    # Frame de captura
    capture_frame = ttk.Frame(root, padding=20)
    capture_frame.configure(style="TFrame")

    title_label = ttk.Label(capture_frame, text="", font=('Helvetica', 14, 'bold'))
    capture_label = ttk.Label(capture_frame, text="Not capturing data.", justify="center")

    capture_label.pack(pady=20)

    start_button = ttk.Button(capture_frame, text="Start Capture", state=tk.DISABLED, command=start_capture)
    start_button.pack(pady=10)
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    
    root.after(1000, check_fitbit_authentication)
    root.mainloop()

# Función para iniciar el servidor Flask en un hilo separado
def start_flask_server():
    app.run(port=5000, debug=False)

if __name__ == '__main__':
    # Iniciar el servidor Flask en un hilo separado
    flask_thread = Thread(target=start_flask_server)
    flask_thread.start()

    # Iniciar la interfaz gráfica en el hilo principal
    start_gui()
