import sys
from PyQt5.QtWidgets import (QApplication, QWidget, QLineEdit, QPushButton,
                             QVBoxLayout, QHBoxLayout, QProgressBar, QTextEdit,
                             QListWidget, QMessageBox, QTabWidget)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QIcon
import os
import requests
from bs4 import BeautifulSoup
import json
from time import sleep
from datetime import datetime

class DownloadThread(QThread):
    update_progress = pyqtSignal(int)
    update_log = pyqtSignal(str)
    download_complete = pyqtSignal()

    def __init__(self, userslist):
        super().__init__()
        self.userslist = userslist
        self.is_cancelled = False

    def run(self):

        script_dir = os.path.dirname(os.path.abspath(__file__))
        base_path = os.path.join(script_dir, "Downloads")

        for idx, username in enumerate(self.userslist):
            if self.is_cancelled:
                break

            user_path = os.path.join(base_path, username)
            os.makedirs(user_path, exist_ok=True)

            from datetime import datetime
            date_folder = datetime.now().strftime("%Y-%m-%d")
            download_path = os.path.join(user_path, date_folder)
            os.makedirs(download_path, exist_ok=True)

            os.chdir(download_path)

            json_dict = self.get_json(username)
            if json_dict:
                self.download_media(json_dict)
            self.update_progress.emit((idx + 1) * 100 // len(self.userslist))

        self.download_complete.emit()

    def get_json(self, username):
        base_url = "https://story.snapchat.com/@"
        headers = {'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:94.0) Gecko/20100101 Firefox/103.0.2'}
        mix = base_url + username
        r = requests.get(mix, headers=headers)

        if not r.ok:
            self.update_log.emit("Oh Snap! No connection with Snap!")
            return None

        soup = BeautifulSoup(r.content, "html.parser")
        snaps = soup.find(id="__NEXT_DATA__").string.strip()
        data = json.loads(snaps)

        return data

    def download_media(self, json_dict):
        try:
            for i in json_dict["props"]["pageProps"]["story"]["snapList"]:
                if self.is_cancelled:
                    return

                retries = 3
                while retries > 0 and not self.is_cancelled:
                    try:
                        file_url = i["snapUrls"]["mediaUrl"]
                        if not file_url:
                            self.update_log.emit("There is a Story but no URL is provided by Snapchat.")
                            break

                        r = requests.get(file_url, stream=True, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)

                        if "image" in r.headers['Content-Type']:
                            file_name = r.headers['ETag'].replace('"', '') + ".jpeg"
                        elif "video" in r.headers['Content-Type']:
                            file_name = r.headers['ETag'].replace('"', '') + ".mp4"
                        else:
                            continue

                        current_dir = os.getcwd()
                        full_path = os.path.join(current_dir, file_name)

                        if os.path.isfile(full_path):
                            self.update_log.emit(f"File already exists: {file_name}")
                            break

                        sleep(0.3)

                        if r.status_code == 200:
                            with open(full_path, 'wb') as f:
                                for chunk in r:
                                    f.write(chunk)
                            self.update_log.emit(f"Downloaded {file_name}")
                            break  
                        else:
                            self.update_log.emit("[-] Cannot make connection to download media!")
                            break
                    except requests.RequestException as e:
                        if self.is_cancelled:
                            return
                        retries -= 1
                        if retries == 0:
                            self.update_log.emit(f"Failed to download after 3 attempts: {str(e)}")
                        else:
                            sleep(1)
                            continue
        except KeyError:
            self.update_log.emit("[-] No stories found for the last 24h.\n")

class SnapchatDownloader(QWidget):
    def __init__(self):
        super().__init__()
        self.userslist = []
        self.favorites = []
        self.history = []
        self.download_queue = []
        self.is_downloading = False
        self.initUI()
        self.load_data()

    def initUI(self):
        self.setWindowTitle('Snapchat Downloader')
        self.setWindowIcon(QIcon('snap.png'))

        main_layout = QVBoxLayout()

        self.tab_widget = QTabWidget()

        users_tab = QWidget()
        users_layout = QVBoxLayout()

        self.new_user_input = QLineEdit()
        self.new_user_input.setPlaceholderText('Enter Snapchat username')
        self.add_user_button = QPushButton('Add User')

        input_layout = QHBoxLayout()
        input_layout.addWidget(self.new_user_input)
        input_layout.addWidget(self.add_user_button)

        lists_layout = QHBoxLayout()

        users_list_layout = QVBoxLayout()
        self.user_list_widget = QListWidget()
        self.user_list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        self.user_list_widget.itemDoubleClicked.connect(self.add_to_download_queue)
        users_list_layout.addWidget(QPushButton('Available Users'))
        users_list_layout.addWidget(self.user_list_widget)

        favorites_layout = QVBoxLayout()
        self.favorites_widget = QListWidget()
        self.favorites_widget.setSelectionMode(QListWidget.ExtendedSelection)
        self.favorites_widget.itemDoubleClicked.connect(self.add_to_download_queue)
        favorites_layout.addWidget(QPushButton('Favorites'))
        favorites_layout.addWidget(self.favorites_widget)

        queue_layout = QVBoxLayout()
        self.queue_widget = QListWidget()
        self.queue_widget.setSelectionMode(QListWidget.ExtendedSelection)
        queue_layout.addWidget(QPushButton('Download Queue'))
        queue_layout.addWidget(self.queue_widget)

        lists_layout.addLayout(users_list_layout)
        lists_layout.addLayout(favorites_layout)
        lists_layout.addLayout(queue_layout)

        button_layout = QHBoxLayout()
        self.add_to_favorites = QPushButton('Add to Favorites')
        self.remove_from_favorites = QPushButton('Remove from Favorites')
        self.add_all_to_queue = QPushButton('Add All to Queue')
        self.clear_queue = QPushButton('Clear Queue')
        self.remove_selected = QPushButton('Remove Selected')

        button_layout.addWidget(self.add_to_favorites)
        button_layout.addWidget(self.remove_from_favorites)
        button_layout.addWidget(self.add_all_to_queue)
        button_layout.addWidget(self.clear_queue)
        button_layout.addWidget(self.remove_selected)

        self.progress_bar = QProgressBar()
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.download_button = QPushButton('Download')

        users_layout.addLayout(input_layout)
        users_layout.addLayout(lists_layout)
        users_layout.addLayout(button_layout)
        users_layout.addWidget(self.progress_bar)
        users_layout.addWidget(self.log_area)
        users_layout.addWidget(self.download_button)

        users_tab.setLayout(users_layout)
        self.tab_widget.addTab(users_tab, "Users")

        history_tab = QWidget()
        history_layout = QVBoxLayout()
        self.history_widget = QListWidget()
        self.history_widget.setSelectionMode(QListWidget.ExtendedSelection)
        self.history_widget.itemDoubleClicked.connect(self.add_history_to_available)

        self.clear_history_button = QPushButton('Clear History')
        self.clear_history_button.clicked.connect(self.clear_history)

        history_layout.addWidget(QPushButton('Download History'))
        history_layout.addWidget(self.history_widget)
        history_layout.addWidget(self.clear_history_button)
        history_tab.setLayout(history_layout)
        self.tab_widget.addTab(history_tab, "History")

        main_layout.addWidget(self.tab_widget)
        self.setLayout(main_layout)
        self.resize(800, 600)

        self.add_user_button.clicked.connect(self.add_user)
        self.add_to_favorites.clicked.connect(self.add_selected_to_favorites)
        self.remove_from_favorites.clicked.connect(self.remove_selected_from_favorites)
        self.add_all_to_queue.clicked.connect(self.add_all_to_download_queue)
        self.clear_queue.clicked.connect(self.clear_download_queue)
        self.remove_selected.clicked.connect(self.remove_selected_items)
        self.download_button.clicked.connect(self.start_download)

    def load_data(self):
        try:
            with open('snapchat_data.json', 'r') as f:
                data = json.load(f)
                self.userslist = data.get('users', [])
                self.favorites = data.get('favorites', [])
                self.history = data.get('history', [])

                self.user_list_widget.clear()
                self.favorites_widget.clear()
                self.history_widget.clear()

                self.user_list_widget.addItems(self.userslist)
                self.favorites_widget.addItems(self.favorites)
                self.history_widget.addItems(self.history)
        except FileNotFoundError:
            pass

    def save_data(self):
        data = {
            'users': self.userslist,
            'favorites': self.favorites,
            'history': self.history
        }
        with open('snapchat_data.json', 'w') as f:
            json.dump(data, f, indent=4)

    def add_user(self):
        new_user = self.new_user_input.text().strip()
        if new_user and new_user not in self.userslist:
            self.userslist.append(new_user)
            self.user_list_widget.addItem(new_user)
            self.new_user_input.clear()
            self.save_data()
        else:
            QMessageBox.warning(self, "Error", "Invalid or duplicate username.")

    def add_selected_to_favorites(self):
        selected_items = self.user_list_widget.selectedItems()
        for item in selected_items:
            username = item.text()
            if username not in self.favorites:
                self.favorites.append(username)
                self.favorites_widget.addItem(username)
        self.save_data()

    def remove_selected_from_favorites(self):
        selected_items = self.favorites_widget.selectedItems()
        for item in selected_items:
            self.favorites.remove(item.text())
            self.favorites_widget.takeItem(self.favorites_widget.row(item))
        self.save_data()

    def add_to_download_queue(self, item):
        username = item.text()
        if username not in [self.queue_widget.item(i).text() 
                          for i in range(self.queue_widget.count())]:
            self.queue_widget.addItem(username)
            self.download_queue.append(username)

    def add_all_to_download_queue(self):
        source_widget = self.tab_widget.currentWidget().findChild(QListWidget)
        if source_widget:
            for i in range(source_widget.count()):
                username = source_widget.item(i).text()
                if username not in [self.queue_widget.item(i).text() 
                                  for i in range(self.queue_widget.count())]:
                    self.queue_widget.addItem(username)
                    self.download_queue.append(username)

    def clear_download_queue(self):
        self.queue_widget.clear()
        self.download_queue.clear()

    def remove_selected_items(self):
        current_widget = self.tab_widget.currentWidget().findChild(QListWidget)
        if current_widget:
            selected_items = current_widget.selectedItems()
            for item in selected_items:
                if current_widget == self.user_list_widget:
                    self.userslist.remove(item.text())
                elif current_widget == self.queue_widget:
                    self.download_queue.remove(item.text())
                current_widget.takeItem(current_widget.row(item))
            self.save_data()

    def start_download(self):
        if not self.download_queue:
            QMessageBox.warning(self, "Error", "Please add users to download queue first.")
            return

        if self.is_downloading:
            self.thread.is_cancelled = True
            self.download_button.setDisabled(True)
            self.download_button.setText('Cancelling...')
            return

        self.is_downloading = True
        self.download_button.setText('Cancel Download')
        self.download_button.setEnabled(True)
        self.log_area.clear()
        self.progress_bar.setValue(0)

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for username in self.download_queue:
            history_entry = f"{username} - {current_time}"
            self.history.append(history_entry)
            self.history_widget.addItem(history_entry)

        self.thread = DownloadThread(self.download_queue)
        self.thread.update_progress.connect(self.update_progress)
        self.thread.update_log.connect(self.update_log)
        self.thread.download_complete.connect(self.download_complete)
        self.thread.start()
        self.save_data()

    def download_complete(self):
        self.is_downloading = False
        self.download_button.setText('Download')
        self.download_button.setEnabled(True)
        self.progress_bar.setValue(0)
        if not self.thread.is_cancelled:
            QMessageBox.information(self, "Download Complete", "Downloaded successfully.")
            self.clear_download_queue()
        else:
            self.log_area.append("Download cancelled by user.")

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def update_log(self, message):
        self.log_area.append(message)

    def add_history_to_available(self, item):

        username = item.text().split(' - ')[0]
        if username not in self.userslist:
            self.userslist.append(username)
            self.user_list_widget.addItem(username)
            self.save_data()
            QMessageBox.information(self, "Success", f"Added {username} to available users.")
        else:
            QMessageBox.information(self, "Info", f"{username} is already in available users.")

    def clear_history(self):
        reply = QMessageBox.question(self, 'Clear History', 
                                   'Are you sure you want to clear the download history?',
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            self.history.clear()
            self.history_widget.clear()
            self.save_data()
            QMessageBox.information(self, "Success", "History cleared successfully.")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = SnapchatDownloader()
    ex.show()
    sys.exit(app.exec_())
