import threading
import requests

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.core.window import Window

Window.clearcolor = (0.025, 0.035, 0.08, 1)

class FridayApp(App):
    def build(self):
        self.api_key = ""

        root = BoxLayout(orientation="vertical", padding=12, spacing=10)

        title = Label(
            text="[b]F.R.I.D.A.Y[/b]\nYour Personal AI Assistant",
            markup=True,
            size_hint_y=None,
            height=75,
            font_size=23
        )
        root.add_widget(title)

        self.key_input = TextInput(
            hint_text="Gemini API Key (Settings)",
            password=True,
            multiline=False,
            size_hint_y=None,
            height=48
        )
        root.add_widget(self.key_input)

        self.save_button = Button(
            text="Save API Key",
            size_hint_y=None,
            height=45
        )
        self.save_button.bind(on_press=self.save_key)
        root.add_widget(self.save_button)

        scroll = ScrollView()
        self.chat = Label(
            text="FRIDAY: Hello! Main online hone ke liye taiyar hoon.",
            size_hint_y=None,
            halign="left",
            valign="top",
            markup=True
        )
        self.chat.bind(
            texture_size=lambda obj, size: setattr(obj, "height", size[1])
        )
        self.chat.bind(width=lambda obj, width: setattr(obj, "text_size", (width, None)))
        scroll.add_widget(self.chat)
        root.add_widget(scroll)

        self.message = TextInput(
            hint_text="Type your message...",
            multiline=False,
            size_hint_y=None,
            height=52
        )
        root.add_widget(self.message)

        send = Button(text="SEND", size_hint_y=None, height=50)
        send.bind(on_press=self.send_message)
        root.add_widget(send)

        return root

    def save_key(self, instance):
        self.api_key = self.key_input.text.strip()
        self.chat.text += "\n\nFRIDAY: API Key saved for this session."

    def send_message(self, instance):
        question = self.message.text.strip()
        if not question:
            return

        if not self.api_key:
            self.chat.text += "\n\nFRIDAY: Pehle Gemini API Key enter karein."
            return

        self.message.text = ""
        self.chat.text += "\n\nYou: " + question + "\n\nFRIDAY: Soch raha hoon..."

        threading.Thread(
            target=self.ask_gemini,
            args=(question,),
            daemon=True
        ).start()

    def ask_gemini(self, question):
        try:
            url = (
                "https://generativelanguage.googleapis.com/v1beta/"
                "models/gemini-2.5-flash:generateContent"
            )

            response = requests.post(
                url,
                params={"key": self.api_key},
                json={
                    "contents": [{
                        "parts": [{
                            "text": "You are FRIDAY, a helpful personal AI assistant. "
                                    "Reply naturally in Hindi or English. User says: "
                                    + question
                        }]
                    }]
                },
                timeout=45
            )

            data = response.json()
            if response.status_code != 200:
                answer = "Gemini Error: " + str(data.get("error", {}).get("message", response.status_code))
            else:
                answer = data["candidates"][0]["content"]["parts"][0]["text"]

        except Exception as error:
            answer = "Connection problem: " + str(error)

        Clock.schedule_once(lambda dt: self.show_answer(answer))

    def show_answer(self, answer):
        self.chat.text += "\n\nFRIDAY: " + answer

if __name__ == "__main__":
    FridayApp().run()
