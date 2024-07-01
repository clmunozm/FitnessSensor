import requests
from flask import Flask, request, redirect
import webbrowser
import os
import time
from threading import Thread
from dotenv import load_dotenv

# Cargar las variables de entorno desde el archivo .env
load_dotenv()

# Configuración de la aplicación Fitbit desde las variables de entorno
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
REDIRECT_URI = 'http://localhost:5000/bgames/fitness'
AUTHORIZATION_BASE_URL = 'https://www.fitbit.com/oauth2/authorize'
TOKEN_URL = 'https://api.fitbit.com/oauth2/token'
SCOPES = ['activity', 'nutrition', 'sleep', 'heartrate', 'weight', 'profile']

app = Flask(__name__)
access_token = None

# Ruta para iniciar el proceso de autorización
@app.route('/')
def login():
    auth_url = f"{AUTHORIZATION_BASE_URL}?response_type=code&client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&scope={' '.join(SCOPES)}"
    return redirect(auth_url)

# Ruta para manejar el callback de OAuth2.0
@app.route('/bgames/fitness')
def callback():
    global access_token
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
        
        return f"Authentication successful! The access token is: {access_token}"
    else:
        return f"Error: {token_response}"

# Función para obtener datos de Fitbit
def get_fitbit_data(endpoint):
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    response = requests.get(f'https://api.fitbit.com/1/user/-/{endpoint}.json', headers=headers)
    return response.json()

if __name__ == '__main__':
    # Abrir el navegador para iniciar el proceso de autenticación
    webbrowser.open('http://localhost:5000/')
    
    # Iniciar la aplicación Flask en un hilo separado
    server = Thread(target=app.run, kwargs={'debug': True, 'use_reloader': False})
    server.start()
    
    # Esperar hasta que el token de acceso esté disponible
    while access_token is None:
        print("Waiting for access token...")
        time.sleep(2)
    
    # Una vez que el token de acceso esté disponible, puedes hacer solicitudes a la API de Fitbit
    print("Access token obtained. Fetching Fitbit data...")
    
    # Ejemplo: obtener datos de actividad del día actual
    activity_data = get_fitbit_data('activities/date/today')
    print("Activity Data:")
    print(activity_data)
    
    # Puedes cambiar el endpoint para obtener diferentes tipos de datos
    # Ejemplo: obtener datos del sueño
    # sleep_data = get_fitbit_data('sleep/date/today')
    # print("Sleep Data:")
    # print(sleep_data)
