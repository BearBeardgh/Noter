import sys
import time
import threading
import json
import os
from datetime import datetime, timedelta
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import *
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QColor, QPalette



SESSIONS_FILE = os.path.join(os.path.dirname(__file__),"sessions.json")
print(f"Sessions file path: {SESSIONS_FILE}")

def load_sessions():
    """Cargar las sesiones desde el archivo JSON."""
    print(f"Trying to load from {SESSIONS_FILE}")
    try:
        with open(SESSIONS_FILE, "r") as file:
            # Asegurarse de que cada sesión tenga los campos necesarios,
            # incluso si son None o vacíos, para compatibilidad.
            sessions_data = json.load(file)
            for session in sessions_data:
                session.setdefault('composer', 'Unknown')
                session.setdefault('work', 'Unknown')
                session.setdefault('movement', 'Unknown')
                session.setdefault('notes', '') # Asegurar que notes exista
            return sessions_data
    except FileNotFoundError:
        print(f"File not found: {SESSIONS_FILE}")
        return []
    except json.JSONDecodeError:
        print(f"Error decoding JSON from {SESSIONS_FILE}. Returning empty list.")
        return []
    except Exception as e:
        print(f"An unexpected error occurred loading sessions: {e}")
        return []
    
def save_session(sessions, session):
    """Guardar una nueva sesión en el archivo JSON."""
    print(f"Trying to save on {SESSIONS_FILE}")
    try:
        # --- Validaciones y valores por defecto ---
        # Asegurarse de que los campos jerárquicos existan
        session['composer'] = session.get('composer', 'Unknown') or 'Unknown'
        session['work'] = session.get('work', 'Unknown') or 'Unknown'
        session['movement'] = session.get('movement', 'Unknown') or 'Unknown'
        session['notes'] = session.get('notes', '') # Asegurar que notes exista

        # Redondear la duración a segundos (ya estaba en segundos, pero la conversión a minutos era incorrecta)
        # La duración ya viene en segundos de timer.get_total_time()
        # session['duration'] = round(session['duration']) # Redondear a segundos enteros si es necesario

        # Agregar campos adicionales para consultas futuras
        session_date_str = session['date'] # Ya debería estar en formato 'YYYY-MM-DD'
        session_date = datetime.strptime(session_date_str, '%Y-%m-%d')
        session['week'] = session_date.isocalendar()[1]
        session['month'] = session_date.month
        session['year'] = session_date.year

        sessions.append(session)
        with open(SESSIONS_FILE, "w") as file:
            json.dump(sessions, file, indent=4)
        print(f"session saved: {session}")
    except Exception as e:
        print(f"Error saving session: {e}")



def calculate_period_stats(sessions, period_type):
    """Calcular estadísticas basadas en el tipo de período."""
    if not sessions:
        return []

    # Obtener la fecha y hora actual
    now = datetime.now()

    # Filtrar sesiones según el período
    valid_sessions = []
    for session in sessions:
        session_date = datetime.strptime(session['date'], '%Y-%m-%d')

        if period_type == 'daily':
            # Solo sesiones del día actual
            if session_date.date() == now.date():
                valid_sessions.append(session)
        elif period_type == 'weekly':
            # Solo sesiones de la última semana (7 días)
            if now.date() - session_date.date() <= timedelta(days=7):
                valid_sessions.append(session)
        elif period_type == 'monthly':
            # Solo sesiones del último mes (30 días)
            if now.date() - session_date.date() <= timedelta(days=30):
                valid_sessions.append(session)
        elif period_type == 'yearly':
            # Solo sesiones del último año (365 días)
            if now.date() - session_date.date() <= timedelta(days=365):
                valid_sessions.append(session)

    # Calcular estadísticas solo con las sesiones válidas
    stats = {}
    for session in valid_sessions:
        date = session['date']
        duration = session['duration']
        if date in stats:
            stats[date] += duration
        else:
            stats[date] = duration

    return list(stats.items())


def calculate_progress(period_type, total_duration):
    """Calcular el progreso en comparación con las metas."""
    goals = {
        'daily': 5 * 60,      # 5 horas diarias (convertidas a minutos)
        'weekly': 25 * 60,     # 25 horas semanales (convertidas a minutos)
        'monthly': 100 * 60,   # 100 horas mensuales (convertidas a minutos)
        'yearly': 1200 * 60    # 1200 horas anuales (convertidas a minutos)
    }
    goal = goals.get(period_type, 0)
    if goal == 0:
        return 0
    return (total_duration / goal) * 100


def generate_progress_bar(percentage, width=20):
    """Generar una barra de progreso en formato de texto."""
    filled = int(percentage * width / 100)
    empty = width - filled
    return f"[{'#' * filled}{'.' * empty}] {percentage:.1f}%"


def calculate_streak(sessions):
    """Calcular la racha actual de días consecutivos con sesiones de práctica."""
    if not sessions:
        return 0

    # Ordenar las sesiones por fecha (de más reciente a más antigua)
    sessions.sort(key=lambda x: x['date'], reverse=True)

    streak = 0
    previous_date = datetime.strptime(sessions[0]['date'], '%Y-%m-%d').date()

    for session in sessions:
        current_date = datetime.strptime(session['date'], '%Y-%m-%d').date()
        if (previous_date - current_date).days == 1:
            streak += 1
            previous_date = current_date
        elif (previous_date - current_date).days == 0:
            continue  # Misma fecha, no cuenta como un nuevo día
        else:
            break  # Se rompe la racha

    return streak + 1  # Sumar 1 para incluir el día actual


# Clase de cronómetro para la aplicación
class PracticeTimer:
    def __init__(self):
        self.start_time = None
        self.total_time = 0
        self.running = False

    def start(self):
        if not self.running:
            self.start_time = time.time()
            self.running = True

    def stop(self):
        if self.running:
            self.total_time += time.time() - self.start_time
            self.start_time = None
            self.running = False

    def reset(self):
        self.start_time = None
        self.total_time = 0
        self.running = False

    def get_total_time(self):
        if self.running:
            return self.total_time + (time.time() - self.start_time)
        return self.total_time

class CountdownTimer:
    def __init__(self):
        self.total_seconds = 0
        self.running = False
        self.thread = None

    def set_time(self, hours, minutes, seconds):
        self.total_seconds = hours * 3600 + minutes * 60 + seconds

    def start(self, update_callback, finished_callback):
        if self.running:
            return
        self.running = True

        def run():
            while self.total_seconds > 0 and self.running:
                time.sleep(1)
                self.total_seconds -= 1
                formatted = self.format_time(self.total_seconds)
                update_callback(formatted)

            if self.running:
                finished_callback()
            self.running = False

        self.thread = threading.Thread(target=run)
        self.thread.start()

    def stop(self):
        self.running = False

    def format_time(self, seconds):
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h:02}:{m:02}:{s:02}"


class Metronome:
    def __init__(self):
        self.bpm = 60
        self.running = False
        self.thread = None

    def set_bpm(self, bpm):
        if bpm < 20:
            bpm = 20
        elif bpm > 300:
            bpm = 300
        self.bpm = bpm

    def start(self):
        if self.running:
            return
        self.running = True

        def run():
            interval = 60 / self.bpm
            while self.running:
                print("Tick")  # Aquí podrías reproducir un sonido si quieres
                time.sleep(interval)

        self.thread = threading.Thread(target=run)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread is not None:
            self.thread.join()


class CronometroTab(QtWidgets.QWidget):
    def __init__(self, parent_window):
        super().__init__()
        self.parent_window = parent_window
        self.timer = PracticeTimer()
        self.start_time = None
        self.init_ui()

    def init_ui(self):
        self.layout = QtWidgets.QVBoxLayout()

        # --- Campos para Compositor, Obra, Movimiento ---
        details_layout = QtWidgets.QFormLayout()
        self.composer_edit = QtWidgets.QLineEdit()
        self.work_edit = QtWidgets.QLineEdit()
        self.movement_edit = QtWidgets.QLineEdit()
        details_layout.addRow("Compositor:", self.composer_edit)
        details_layout.addRow("Obra:", self.work_edit)
        details_layout.addRow("Movimiento:", self.movement_edit)
        self.layout.addLayout(details_layout)
        # -------------------------------------------------

        self.timer_button = QtWidgets.QPushButton('Iniciar Cronómetro')
        self.timer_button.clicked.connect(self.toggle_timer)
        self.time_label = QtWidgets.QLabel('Tiempo: 00:00:00') # Cambiado formato inicial

        self.layout.addWidget(self.time_label)
        self.layout.addWidget(self.timer_button)

        self.notes_edit = QtWidgets.QTextEdit()
        self.notes_edit.setPlaceholderText("Ingresa tus notas de práctica aquí...")
        # El botón de guardar notas separado es redundante si guardamos al detener
        # self.save_notes_button = QtWidgets.QPushButton("Guardar Notas")
        # self.save_notes_button.clicked.connect(self.save_notes)

        self.layout.addWidget(QtWidgets.QLabel("Notas:")) # Etiqueta para notas
        self.layout.addWidget(self.notes_edit)
        # self.layout.addWidget(self.save_notes_button) # Quitar botón redundante

        self.setLayout(self.layout)

    def toggle_timer(self):
        if self.timer.start_time is None: # Iniciar
            self.timer.start()
            self.start_time = datetime.now().isoformat(timespec='seconds') # Registrar tiempo de inicio
            self.timer_button.setText('Detener Cronómetro y Guardar Sesión')
            self.update_timer() # Iniciar actualización de la etiqueta
        else: # Detener y Guardar
            self.timer.stop()
            end_time = datetime.now().isoformat(timespec='seconds') # Registrar tiempo de fin
            duration_seconds = self.timer.get_total_time() # Obtener duración en segundos
            date = datetime.now().date().isoformat() # Formato YYYY-MM-DD
            notes = self.notes_edit.toPlainText()
            composer = self.composer_edit.text()
            work = self.work_edit.text()
            movement = self.movement_edit.text()

            # Validar que al menos haya duración
            if duration_seconds < 1:
                 QMessageBox.warning(self, "Sesión no guardada", "La duración de la práctica fue demasiado corta.")
                 # Reiniciar sin guardar
                 self.timer.reset()
                 self.time_label.setText('Tiempo: 00:00:00')
                 self.timer_button.setText('Iniciar Cronómetro')
                 self.start_time = None
                 # No limpiar campos de texto para que el usuario no los pierda
                 return # Salir sin guardar

            # Guardar la sesión en el archivo JSON
            session = {
                "start_time": self.start_time,
                "end_time": end_time,
                "duration": duration_seconds, # Guardar en segundos
                "date": date,
                "composer": composer,
                "work": work,
                "movement": movement,
                "notes": notes
            }
            # Usar la lista de sesiones del padre y la función save_session global
            save_session(self.parent_window.sessions, session)

            # Mostrar mensaje de confirmación
            duration_min = duration_seconds / 60
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle('Sesión Guardada')
            msg.setText(f"Sesión de práctica guardada:\n"
                        f"Compositor: {composer or 'N/A'}\n"
                        f"Obra: {work or 'N/A'}\n"
                        f"Movimiento: {movement or 'N/A'}\n"
                        f"Duración: {duration_min:.2f} minutos\n"
                        f"Fecha: {date}")
            msg.exec_()

            # Reiniciar el contador y la interfaz
            self.timer.reset()
            self.time_label.setText('Tiempo: 00:00:00')
            self.timer_button.setText('Iniciar Cronómetro')
            self.start_time = None
            self.notes_edit.clear()
            # Opcional: Limpiar también los campos de compositor/obra/movimiento
            # self.composer_edit.clear()
            # self.work_edit.clear()
            # self.movement_edit.clear()

            # Actualizar otras pestañas (Estadísticas y Logs)
            self.parent_window.refresh_data() # Llamar a una función centralizada en MusicApp


    def update_timer(self):
        if self.timer.start_time is not None:
            elapsed_time = time.time() - self.timer.start_time
            hours = int(elapsed_time // 3600)
            minutes = int((elapsed_time % 3600) // 60)
            seconds = int(elapsed_time % 60)
            self.time_label.setText(f'Tiempo: {hours:02}:{minutes:02}:{seconds:02}')
            # Usar QTimer para la actualización en el hilo de la GUI
            if self.timer.start_time is not None: # Comprobar de nuevo por si se detuvo mientras tanto
                 QTimer.singleShot(100, self.update_timer) # Reprogramar

    # La función save_notes separada ya no es necesaria si guardamos al detener.
    # def save_notes(self):
    #     # ... (código anterior) ...
    #     pass

# ... (Clase NotesTab - parece redundante ahora, considerar eliminarla) ...

# ... (Clases TemporizadorTab, MetronomoTab, EstadisticasTab) ...

# --- Asegúrate de que EstadisticasTab use la duración en segundos ---
# En calculate_period_stats, la duración ya está en segundos (o debería estarlo después del cambio en save_session)
# En calculate_progress, las metas deben estar en segundos
def calculate_progress(period_type, total_duration_seconds):
    """Calcular el progreso en comparación con las metas (en segundos)."""
    goals_hours = {
        'daily': 5,      # 5 horas diarias
        'weekly': 25,     # 25 horas semanales
        'monthly': 100,   # 100 horas mensuales
        'yearly': 1200    # 1200 horas anuales
    }
    # Convertir metas a segundos
    goal_seconds = goals_hours.get(period_type, 0) * 3600
    if goal_seconds == 0:
        return 0
    # total_duration ya está en segundos
    return (total_duration_seconds / goal_seconds) * 100

# En EstadisticasTab.update_progress, asegúrate de que total_duration se maneje como segundos
# (El código actual ya suma las duraciones, que ahora son segundos, así que debería funcionar)

class NotesTab(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.parent_window = parent # added parent
        self.init_ui()

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout()
        self.notes_edit = QtWidgets.QTextEdit()
        self.save_button = QtWidgets.QPushButton("Save Notes")
        self.save_button.clicked.connect(self.save_notes) # Connect to your save function
        layout.addWidget(self.notes_edit)
        layout.addWidget(self.save_button)
        self.setLayout(layout)

    def save_session(sessions, session):
        """Guardar una nueva sesión en el archivo JSON."""
        print(f"Trying to save on {SESSIONS_FILE}")
        try:
            sessions.append(session)
            with open(SESSIONS_FILE, "w") as file:
             json.dump(sessions, file, indent=4)
            print(f"session saved: {session}")
        except Exception as e:
            print(f"Error saving session: {e}")






# Clase de temporizador para la aplicación
class TemporizadorTab(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.layout = QtWidgets.QVBoxLayout()

        self.time_input_layout = QtWidgets.QHBoxLayout()
        self.hours_input = QtWidgets.QSpinBox()
        self.hours_input.setRange(0, 24)
        self.minutes_input = QtWidgets.QSpinBox()
        self.minutes_input.setRange(0, 59)
        self.seconds_input = QtWidgets.QSpinBox()
        self.seconds_input.setRange(0, 59)

        self.time_input_layout.addWidget(QtWidgets.QLabel('Horas:'))
        self.time_input_layout.addWidget(self.hours_input)
        self.time_input_layout.addWidget(QtWidgets.QLabel('Minutos:'))
        self.time_input_layout.addWidget(self.minutes_input)
        self.time_input_layout.addWidget(QtWidgets.QLabel('Segundos:'))
        self.time_input_layout.addWidget(self.seconds_input)

        self.start_button = QtWidgets.QPushButton('Iniciar Temporizador')
        self.start_button.clicked.connect(self.start_timer)

        self.stop_button = QtWidgets.QPushButton('Detener Temporizador')
        self.stop_button.clicked.connect(self.stop_timer)

        self.time_label = QtWidgets.QLabel('00:00:00')

        self.layout.addLayout(self.time_input_layout)
        self.layout.addWidget(self.start_button)
        self.layout.addWidget(self.stop_button)
        self.layout.addWidget(self.time_label)

        self.setLayout(self.layout)

    def start_timer(self):
        hours = self.hours_input.value()
        minutes = self.minutes_input.value()
        seconds = self.seconds_input.value()
        self.timer.set_time(hours, minutes, seconds)
        self.timer.start(self.update_timer, self.timer_finished)

    def stop_timer(self):
        self.timer.stop()
        self.time_label.setText('00:00:00')

    def update_timer(self, formatted_time):
        self.time_label.setText(formatted_time)

    def timer_finished(self):
        self.time_label.setText('¡Tiempo finalizado!')

# Clase de metrómono para la aplicación
class MetronomoTab(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.metronome = Metronome()
        self.init_ui()

    def init_ui(self):
        self.layout = QtWidgets.QVBoxLayout()

        self.bpm_label = QtWidgets.QLabel('BPM: 60')
        self.increase_bpm_button = QtWidgets.QPushButton('Aumentar BPM')
        self.decrease_bpm_button = QtWidgets.QPushButton('Disminuir BPM')
        self.toggle_metronome_button = QtWidgets.QPushButton('Iniciar Metrónomo')

        self.increase_bpm_button.clicked.connect(self.increase_bpm)
        self.decrease_bpm_button.clicked.connect(self.decrease_bpm)
        self.toggle_metronome_button.clicked.connect(self.toggle_metronome)

        self.layout.addWidget(self.bpm_label)
        self.layout.addWidget(self.increase_bpm_button)
        self.layout.addWidget(self.decrease_bpm_button)
        self.layout.addWidget(self.toggle_metronome_button)

        self.setLayout(self.layout)

    def increase_bpm(self):
        self.metronome.set_bpm(self.metronome.bpm + 5)
        self.bpm_label.setText(f'BPM: {self.metronome.bpm}')

    def decrease_bpm(self):
        self.metronome.set_bpm(self.metronome.bpm - 5)
        self.bpm_label.setText(f'BPM: {self.metronome.bpm}')

    def toggle_metronome(self):
        if self.metronome.running:
            self.metronome.stop()
            self.toggle_metronome_button.setText('Iniciar Metrónomo')
        else:
            self.metronome.start()
            self.toggle_metronome_button.setText('Detener Metrónomo')



class EstadisticasTab(QtWidgets.QWidget):
    def __init__(self, sessions):
        super().__init__()
        self.sessions = sessions

        self.clock_visible = True 

        self.init_ui()

        # Configurar un temporizador para el reloj parpadeante
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_clock)
        self.timer.start(1000)  # Actualizar cada 1 segundo

        # Estado del parpadeo
        
        
        

    def init_ui(self):
        self.layout = QtWidgets.QVBoxLayout()

        # Reloj parpadeante
        self.clock_label = QtWidgets.QLabel()
        self.clock_label.setStyleSheet("color: red; font-size: 20px; font-family: 'Courier', monospace;")
        self.update_clock()  # Mostrar la hora inicial
        self.layout.addWidget(self.clock_label)

        # Mostrar la racha actual
        self.streak_label = QtWidgets.QLabel('Racha actual: 0 días')
        self.update_streak()

        # Mostrar el progreso
        self.progress_label = QtWidgets.QLabel()
        self.update_progress()

        # Botón para actualizar estadísticas y logs
        self.refresh_button = QtWidgets.QPushButton('Actualizar Todo')
        self.refresh_button.clicked.connect(self.refresh_all)

        self.layout.addWidget(self.streak_label)
        self.layout.addWidget(self.progress_label)
        self.layout.addWidget(self.refresh_button)
        self.setLayout(self.layout)

    def update_clock(self):
        """Actualizar el reloj parpadeante."""
        now = datetime.now()
        date_text = now.strftime("%A %d de %B %Y")  # Formato: martes 11 de marzo 2025
        time_text = now.strftime("%H:%M")  # Formato: 01:50

        # Alternar visibilidad de los números de la hora
        if self.clock_visible:
            clock_text = f"{date_text} {time_text}"
        else:
            # Ocultar los números de la hora (dejando solo las letras)
            time_text_hidden = ''.join([char if not char.isdigit() else ' ' for char in time_text])
            clock_text = f"{date_text} {time_text_hidden}"

        self.clock_label.setText(clock_text)

        # Cambiar el estado del parpadeo
        self.clock_visible = not self.clock_visible


    def refresh_all(self):
        """Actualizar estadísticas y logs."""
        self.update_streak()
        self.update_progress()
        if hasattr(self.parent(), 'logs_tab'):
            self.parent().logs_tab.load_logs()  # Actualizar logs si existe la pestaña

    def update_streak(self):
        """Actualizar la etiqueta de la racha."""
        streak = calculate_streak(self.sessions)
        self.streak_label.setText(f'Racha actual: {streak} días')

    def update_progress(self):
        """Actualizar las barras de progreso."""
        if not self.sessions:
            self.progress_label.setText("No hay sesiones disponibles.")
            return

        progress_text = "Progreso:\n"
        periods = ['daily', 'weekly', 'monthly', 'yearly']
        period_names = {'daily': 'Diario', 'weekly': 'Semanal', 'monthly': 'Mensual', 'yearly': 'Anual'}

        for period in periods:
            data = calculate_period_stats(self.sessions, period)
            if not data:
                progress_text += f"{period_names[period]}: No hay datos\n"
                continue
            total_duration = sum(duration for _, duration in data)
            percentage = calculate_progress(period, total_duration)
            progress_bar = generate_progress_bar(percentage)
            progress_text += f"{period_names[period]}: {progress_bar}\n"

        self.progress_label.setText(progress_text)


class LogsTab(QtWidgets.QWidget):
    def __init__(self, sessions_ref): # Recibe una referencia a la lista de sesiones
        super().__init__()
        # Guardar la referencia, no una copia, para que se actualice
        self.sessions_ref = sessions_ref
        self.init_ui()

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout()

        self.tree = QTreeWidget()
        # Definir las columnas: Jerarquía, Fecha, Duración, Inicio, Fin, Notas
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels(['Item', 'Fecha', 'Duración (H:M:S)', 'Inicio', 'Fin', 'Notas'])
        # Ajustar el tamaño de las columnas (opcional)
        self.tree.setColumnWidth(0, 250) # Columna de jerarquía más ancha
        self.tree.setColumnWidth(1, 100)
        self.tree.setColumnWidth(2, 100)
        self.tree.setColumnWidth(3, 150)
        self.tree.setColumnWidth(4, 150)
        self.tree.setColumnWidth(5, 300) # Columna de notas más ancha
        self.tree.setAlternatingRowColors(True) # Mejorar legibilidad

        self.load_logs() # Carga inicial

        layout.addWidget(self.tree)
        self.setLayout(layout)

    def format_duration(self, total_seconds):
        """Formatea segundos a H:MM:SS"""
        if not isinstance(total_seconds, (int, float)) or total_seconds < 0:
            return "0:00:00"
        total_seconds = int(round(total_seconds))
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours}:{minutes:02}:{seconds:02}"

    def load_logs(self):
        """Cargar y mostrar los logs en una estructura de árbol."""
        self.tree.clear() # Limpiar el árbol antes de recargar
        sessions = self.sessions_ref # Usar la referencia actualizada

        # Estructura para agrupar: {composer: {work: {movement: [sessions]}}}
        grouped_sessions = {}

        # Ordenar sesiones por fecha (opcional, pero bueno para la visualización)
        sessions.sort(key=lambda s: (s.get('composer', 'Unknown'),
                                     s.get('work', 'Unknown'),
                                     s.get('movement', 'Unknown'),
                                     s.get('date', '1970-01-01'), # Fecha por defecto para ordenar
                                     s.get('start_time', '')), reverse=True) # Más recientes primero dentro de cada grupo

        for session in sessions:
            # Usar .get con valor por defecto por si faltan claves en sesiones antiguas
            composer = session.get('composer', 'Unknown') or 'Unknown'
            work = session.get('work', 'Unknown') or 'Unknown'
            movement = session.get('movement', 'Unknown') or 'Unknown'

            # Crear niveles en el diccionario si no existen
            if composer not in grouped_sessions:
                grouped_sessions[composer] = {}
            if work not in grouped_sessions[composer]:
                grouped_sessions[composer][work] = {}
            if movement not in grouped_sessions[composer][work]:
                grouped_sessions[composer][work][movement] = []

            # Añadir la sesión al grupo correspondiente
            grouped_sessions[composer][work][movement].append(session)

        # --- Poblar el QTreeWidget ---
        for composer, works in grouped_sessions.items():
            composer_item = QTreeWidgetItem(self.tree, [composer]) # Item de nivel superior
            composer_item.setExpanded(False) # Empezar colapsado

            for work, movements in works.items():
                work_item = QTreeWidgetItem(composer_item, [work]) # Hijo del compositor
                work_item.setExpanded(False)

                for movement, session_list in movements.items():
                    movement_item = QTreeWidgetItem(work_item, [movement]) # Hijo de la obra
                    movement_item.setExpanded(False)

                    for session in session_list:
                        # Formatear datos para mostrar
                        date = session.get('date', 'N/A')
                        duration_secs = session.get('duration', 0)
                        duration_formatted = self.format_duration(duration_secs)
                        start_time = session.get('start_time', 'N/A')
                        end_time = session.get('end_time', 'N/A')
                        notes = session.get('notes', '')

                        # Crear el item de la sesión (hoja del árbol)
                        # La primera columna es el identificador (usaremos la fecha aquí)
                        # Las otras columnas son los datos específicos
                        log_item = QTreeWidgetItem(movement_item, [
                            f"Sesión del {date}", # Columna 0: Item (descripción)
                            date,                # Columna 1: Fecha
                            duration_formatted,  # Columna 2: Duración
                            start_time,          # Columna 3: Inicio
                            end_time,            # Columna 4: Fin
                            notes                # Columna 5: Notas
                        ])
                        # Opcional: Añadir tooltip con más detalles si se desea
                        log_item.setToolTip(5, notes) # Mostrar notas completas en tooltip

        # Ajustar columnas al contenido después de poblar (opcional)
        # for i in range(self.tree.columnCount()):
        #    self.tree.resizeColumnToContents(i)


# ... (Clases PracticeTimer, CountdownTimer, Metronome) ...

# Paso 4: Modificar `MusicApp` para manejar actualizaciones


# condb.py

# ... (importaciones y clases anteriores) ...

class MusicApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.sessions = load_sessions() # Carga inicial
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Herramienta de Práctica Musical')

        self.tabs = QtWidgets.QTabWidget() # Guardar referencia a las pestañas

        # Crear instancias de las pestañas
        self.cronometro_tab = CronometroTab(self) # Pasa la referencia de MusicApp
        self.temporizador_tab = TemporizadorTab()
        self.metronomo_tab = MetronomoTab()
        self.estadisticas_tab = EstadisticasTab(self.sessions) # Pasa la lista de sesiones
        # Pasar la REFERENCIA a la lista de sesiones a LogsTab
        self.logs_tab = LogsTab(self.sessions)

        # Añadir pestañas
        self.tabs.addTab(self.cronometro_tab, 'Cronómetro')
        self.tabs.addTab(self.temporizador_tab, 'Temporizador')
        self.tabs.addTab(self.metronomo_tab, 'Metrónomo')
        self.tabs.addTab(self.estadisticas_tab, 'Estadísticas')
        self.tabs.addTab(self.logs_tab, 'Logs')

        # No necesitas el QTimer aquí si actualizas después de guardar
        # self.timer = QTimer()
        # self.timer.timeout.connect(self.update_stats) # Renombrar a refresh_data
        # self.timer.start(60000)

        self.setCentralWidget(self.tabs)
        self.resize(900, 700) # Ajustar tamaño para la nueva estructura
        self.show()

    def refresh_data(self):
        """Actualiza los datos en las pestañas que dependen de las sesiones."""
        print("Refreshing data in Stats and Logs tabs...")
        # Recargar sesiones del archivo por si acaso (aunque save_session ya actualiza la lista en memoria)
        # self.sessions = load_sessions() # Opcional: Descomentar si hay modificaciones externas al archivo

        # Actualizar Estadísticas
        if hasattr(self, 'estadisticas_tab'):
            # Pasar la lista actualizada (aunque EstadisticasTab ya tiene una copia inicial)
            # Mejor sería que EstadisticasTab también use la referencia o tenga un método update
            self.estadisticas_tab.sessions = self.sessions # Actualizar la referencia en estadísticas
            self.estadisticas_tab.update_progress()
            self.estadisticas_tab.update_streak()

        # Actualizar Logs
        if hasattr(self, 'logs_tab'):
            # LogsTab ya usa la referencia self.sessions, solo necesita recargar su vista
            self.logs_tab.load_logs()

    # La función update_stats ya no es necesaria si usamos refresh_data
    # def update_stats(self):
    #    self.refresh_data()


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = MusicApp()
    sys.exit(app.exec_())