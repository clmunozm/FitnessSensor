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
    
    if last_date == today:
        # Es el mismo día, calcular puntos para calorías adicionales
        additional_calories = calories_out - last_calories
        if additional_calories > 0:
            points = additional_calories // 100  # 1 punto por cada 100 calorías adicionales
            updated_calories = last_calories + additional_calories
            write_calories_log(today, updated_calories)  # Actualizar el log con las calorías acumuladas
            return points
        else:
            return 0
    else:
        # Es un nuevo día, calcular puntos para todas las calorías y reiniciar el log
        points = calories_out // 100  # 1 punto por cada 100 calorías
        write_calories_log(today, calories_out)
        return points

# Función para enviar los puntos obtenidos a la API
def send_points_to_server(points):
    if points > 0:  # Solo enviar si se han obtenido puntos
        data = {
            "id_player": userID,
            "id_subattributes_conversion_sensor_endpoint": SENSOR_ENDPOINT_ID,
            "new_data": [str(points)]
        }
        response = requests.post(POINTS_URL, json=data)
        if response.status_code == 200:
            print(f"Puntos enviados exitosamente: {points}")
        else:
            print(f"Error al enviar puntos: {response.status_code} - {response.text}")

def start_gui():
    def authenticate():
        username = username_entry.get()
        password = password_entry.get()
        global userID
        userID = get_user_id(username, password)
        print(userID)
        if userID:
            messagebox.showinfo("Success", f"User ID obtained: {userID}")
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
    
    def update_capture_data(calories_out, points, new_calories):
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        title_label.config(text=f"Última vez actualizado: {current_time}")
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
                
                # Calcular nuevas calorías desde la última captura
                last_date, last_calories = read_calories_log()
                if last_date == date.today().isoformat():
                    new_calories = calories_out - last_calories
                else:
                    new_calories = calories_out  # Todas las calorías son nuevas si es un día nuevo

                print(f"New Calories: {new_calories}")
                
                # Calcular puntos y actualizar el registro de calorías procesadas
                points = calculate_points_and_update_log(calories_out)
                print(f"Points earned: {points}")
                
                # Enviar los puntos obtenidos a la API
                send_points_to_server(points)
                
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

    window_width = 600
    window_height = 200
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()

    position_top = int(screen_height/2 - window_height/2)
    position_right = int(screen_width/2 - window_width/2)

    root.geometry(f'{window_width}x{window_height}+{position_right}+{position_top}')

    username_label = tk.Label(root, text="Username:")
    username_label.pack()

    username_entry = tk.Entry(root)
    username_entry.pack()

    password_label = tk.Label(root, text="Password:")
    password_label.pack()

    password_entry = tk.Entry(root, show="*")
    password_entry.pack()

    authenticate_button = tk.Button(root, text="Authenticate", command=authenticate)
    authenticate_button.pack()

    start_button = tk.Button(root, text="Start Capture", state=tk.DISABLED, command=start_capture)
    start_button.pack()

    title_label = tk.Label(root, text="", font=('Helvetica', 12))
    capture_label = tk.Label(root, text="Not capturing data.", font=('Helvetica', 14, 'bold'), justify=tk.CENTER)
    
    # Centrando el texto de las calorías y puntos
    capture_label.pack(pady=20)

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
