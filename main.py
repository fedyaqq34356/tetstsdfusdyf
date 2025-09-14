#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
from datetime import datetime
from telegram_commenter import TelegramCommenter
import time

class TelegramCommenterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("🤖 Telegram Auto Commenter")
        self.root.geometry("900x700")
        self.root.resizable(True, True)
        
        self.commenter = TelegramCommenter()
        self.monitoring_thread = None
        self.monitoring_active = False
        
        self.create_widgets()
    
    def create_widgets(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        accounts_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="👥 Облікові записи", menu=accounts_menu)
        accounts_menu.add_command(label="Додати обліковий запис", command=self.add_account_dialog)
        accounts_menu.add_command(label="Видалити обліковий запис", command=self.remove_account_dialog)
        accounts_menu.add_command(label="Статус облікових записів", command=self.show_accounts_status)
        accounts_menu.add_command(label="Перевірити підключення", command=self.check_connections)
        
        channels_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="📺 Канали", menu=channels_menu)
        channels_menu.add_command(label="Додати канал", command=self.add_channel_dialog)
        channels_menu.add_command(label="Видалити канал", command=self.remove_channel_dialog)
        channels_menu.add_command(label="Призначити облікові записи до каналу", command=self.assign_accounts_to_channel)
        channels_menu.add_command(label="Статус каналів", command=self.show_channels_status)
        
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="⚙️ Налаштування", menu=settings_menu)
        settings_menu.add_command(label="Показати налаштування", command=self.show_settings)
        settings_menu.add_command(label="Змінити налаштування", command=self.change_settings_dialog)
        
        stats_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="📊 Статистика", menu=stats_menu)
        stats_menu.add_command(label="Показати статистику", command=self.show_statistics)
        
        bot_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="🚀 Бот", menu=bot_menu)
        bot_menu.add_command(label="Запустити бота", command=self.start_bot)
        bot_menu.add_command(label="Зупинити бота", command=self.stop_bot)
        
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.log_text = scrolledtext.ScrolledText(main_frame, height=25, width=100)
        self.log_text.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=1, column=0, columnspan=2, pady=10)
        
        ttk.Button(button_frame, text="Оновити статус", command=self.refresh_status).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Очистити лог", command=self.clear_logs).pack(side=tk.LEFT, padx=5)
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=1)
        
        self.log_message("Програма запущена. Використовуйте меню для налаштувань.")
    
    def log_message(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def clear_logs(self):
        self.log_text.delete(1.0, tk.END)
    
    def show_message(self, title, message, type="info"):
        if type == "info":
            messagebox.showinfo(title, message)
        elif type == "warning":
            messagebox.showwarning(title, message)
        elif type == "error":
            messagebox.showerror(title, message)
    
    def input_dialog(self, title, prompt, show_char=None):
        import tkinter.simpledialog as simpledialog
        
        try:
            def log_and_show():
                self.log_message(f"Очікування вводу: {prompt}")
                self.log_message("⚠️ Введіть код у вікні, що з'явиться!")
                
                value = simpledialog.askstring(
                    title, 
                    f"{prompt}\n\nВведіть код і натисніть OK\n(НЕ закривайте вікно!)", 
                    parent=self.root, 
                    show=show_char
                )
                return value
            
            if threading.current_thread() != threading.main_thread():
                result_container = []
                event = threading.Event()
                
                def execute_in_main():
                    try:
                        result = log_and_show()
                        result_container.append(result)
                    except Exception as e:
                        self.log_message(f"Помилка діалогу: {e}")
                        result_container.append(None)
                    finally:
                        event.set()
                
                self.root.after_idle(execute_in_main)
                
                if event.wait(timeout=300):
                    result = result_container[0] if result_container else None
                    if result is None:
                        self.root.after(0, lambda: self.log_message("❌ Код не введено або діалог скасовано"))
                    return result
                else:
                    self.root.after(0, lambda: self.log_message("⏰ Таймаут введення коду"))
                    return None
            else:
                return log_and_show()
                
        except Exception as e:
            self.log_message(f"Критична помилка діалогу: {e}")
            return None
    
    def paste_from_clipboard(self, entry):
        try:
            pasted = self.root.clipboard_get()
            entry.delete(0, tk.END)
            entry.insert(0, pasted)
        except tk.TclError:
            self.show_message("Помилка", "Буфер обміну порожній або недоступний")
    
    def add_account_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Додати обліковий запис")
        dialog.geometry("600x600")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Номер телефону (+380...):").pack(pady=5)
        phone_frame = ttk.Frame(dialog)
        phone_frame.pack(pady=5)
        phone_var = tk.StringVar()
        phone_entry = ttk.Combobox(phone_frame, textvariable=phone_var, values=[acc["phone"] for acc in self.commenter.config["accounts"]])
        phone_entry.pack(side=tk.LEFT)
        ttk.Button(phone_frame, text="Вставити з буфера обміну", command=lambda: self.paste_from_clipboard(phone_entry)).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(dialog, text="API ID:").pack(pady=5)
        api_id_frame = ttk.Frame(dialog)
        api_id_frame.pack(pady=5)
        api_id_entry = ttk.Entry(api_id_frame, width=35)
        api_id_entry.pack(side=tk.LEFT)
        ttk.Button(api_id_frame, text="Вставити з буфера обміну", command=lambda: self.paste_from_clipboard(api_id_entry)).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(dialog, text="API Hash:").pack(pady=5)
        api_hash_frame = ttk.Frame(dialog)
        api_hash_frame.pack(pady=5)
        api_hash_entry = ttk.Entry(api_hash_frame, width=35)
        api_hash_entry.pack(side=tk.LEFT)
        ttk.Button(api_hash_frame, text="Вставити з буфера обміну", command=lambda: self.paste_from_clipboard(api_hash_entry)).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(dialog, text="Ім'я (необов'язково):").pack(pady=5)
        name_entry = ttk.Entry(dialog, width=40)
        name_entry.pack(pady=5)
        
        def submit():
            phone = phone_var.get().strip()
            api_id = api_id_entry.get().strip()
            api_hash = api_hash_entry.get().strip()
            name = name_entry.get().strip()
            
            if self.commenter.add_account(phone, api_id, api_hash, name):
                self.show_message("Успіх", "✅ Обліковий запис додано")
                self.log_message(f"Обліковий запис {phone} додано")
            else:
                self.show_message("Помилка", "⌐ Обліковий запис уже існує", "warning")
            dialog.destroy()
        
        ttk.Button(dialog, text="Додати", command=submit).pack(pady=20)
    
    def remove_account_dialog(self):
        if not self.commenter.config["accounts"]:
            self.show_message("Попередження", "❌ Жодного облікового запису не додано", "warning")
            return
            
        dialog = tk.Toplevel(self.root)
        dialog.title("Видалити обліковий запис")
        dialog.geometry("600x400")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Виберіть обліковий запис для видалення:").pack(pady=5)
        
        accounts_frame = ttk.Frame(dialog)
        accounts_frame.pack(pady=5, fill=tk.BOTH, expand=True)
        
        selected_account = tk.StringVar()
        
        for account in self.commenter.config["accounts"]:
            ttk.Radiobutton(
                accounts_frame, 
                text=f"{account['name']} ({account['phone']})", 
                variable=selected_account,
                value=account['phone']
            ).pack(anchor=tk.W, pady=2)
        
        def submit():
            phone = selected_account.get()
            if not phone:
                self.show_message("Помилка", "❌ Виберіть обліковий запис для видалення", "warning")
                return
                
            if self.commenter.remove_account(phone):
                self.show_message("Успіх", "✅ Обліковий запис видалено")
                self.log_message(f"Обліковий запис {phone} видалено")
            else:
                self.show_message("Помилка", "❌ Обліковий запис не знайдено", "warning")
            dialog.destroy()
        
        ttk.Button(dialog, text="Видалити", command=submit).pack(pady=20)
    
    def add_channel_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Додати канал")
        dialog.geometry("600x600")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Ім'я користувача каналу (без @):").pack(pady=5)
        channel_frame = ttk.Frame(dialog)
        channel_frame.pack(pady=5)
        channel_entry = ttk.Entry(channel_frame, width=35)
        channel_entry.pack(side=tk.LEFT)
        ttk.Button(channel_frame, text="Вставити з буфера обміну", command=lambda: self.paste_from_clipboard(channel_entry)).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(dialog, text="Виберіть облікові записи для цього каналу:").pack(pady=(10,5))
        accounts_frame = ttk.Frame(dialog)
        accounts_frame.pack(pady=5, fill=tk.BOTH, expand=True)
        
        selected_accounts = []
        for account in self.commenter.config["accounts"]:
            var = tk.BooleanVar()
            chk = ttk.Checkbutton(accounts_frame, text=f"{account['name']} ({account['phone']})", variable=var)
            chk.pack(anchor=tk.W)
            selected_accounts.append((account['phone'], var))
        
        def submit():
            channel = channel_entry.get().strip().replace("@", "").replace("https://t.me/", "")
            if not channel:
                self.show_message("Помилка", "⌐ Введіть ім'я користувача каналу", "warning")
                return
            
            assigned_accounts = [phone for phone, var in selected_accounts if var.get()]
            
            if self.commenter.add_channel(channel, assigned_accounts):
                self.show_message("Успіх", f"✅ Канал @{channel} додано з {len(assigned_accounts)} обліковими записами\n⚠️ Переконайтеся, що коментарі в каналі увімкнено!")
                self.log_message(f"Канал @{channel} додано з обліковими записами: {assigned_accounts}")
            else:
                self.show_message("Помилка", "⌐ Канал уже існує", "warning")
            dialog.destroy()
        
        ttk.Button(dialog, text="Додати", command=submit).pack(pady=20)
    
    def assign_accounts_to_channel(self):
        if not self.commenter.config["channels"]:
            self.show_message("Попередження", "⌐ Жодного каналу не додано", "warning")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Призначити облікові записи до каналу")
        dialog.geometry("600x600")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Виберіть канал:").pack(pady=5)
        channel_var = tk.StringVar()
        channel_combo = ttk.Combobox(dialog, textvariable=channel_var, values=[ch['username'] for ch in self.commenter.config["channels"]])
        channel_combo.pack(pady=5)
        
        ttk.Label(dialog, text="Виберіть облікові записи:").pack(pady=(10,5))
        accounts_frame = ttk.Frame(dialog)
        accounts_frame.pack(pady=5, fill=tk.BOTH, expand=True)
        
        selected_accounts = []
        
        def update_accounts(*args):
            for widget in accounts_frame.winfo_children():
                widget.destroy()
            selected_accounts.clear()
            
            channel_username = channel_var.get()
            if not channel_username:
                return
            
            channel_config = next((ch for ch in self.commenter.config["channels"] if ch["username"] == channel_username), None)
            if not channel_config:
                return
            
            assigned_set = set(channel_config.get("accounts", []))
            
            for account in self.commenter.config["accounts"]:  
                var = tk.BooleanVar(value=account["phone"] in assigned_set)
                chk = ttk.Checkbutton(accounts_frame, text=f"{account['name']} ({account['phone']})", variable=var)
                chk.pack(anchor=tk.W)
                selected_accounts.append((account['phone'], var))
        
        channel_var.trace('w', update_accounts)
        
        def submit():
            channel_username = channel_var.get()
            if not channel_username:
                self.show_message("Помилка", "⌐ Виберіть канал", "warning")
                return
            
            assigned_accounts = [phone for phone, var in selected_accounts if var.get()]
            
            if self.commenter.assign_accounts_to_channel(channel_username, assigned_accounts):
                self.show_message("Успіх", f"✅ Облікові записи призначено до @{channel_username}")
                self.log_message(f"Облікові записи {assigned_accounts} призначено до @{channel_username}")
            else:
                self.show_message("Помилка", "⌐ Помилка призначення", "warning")
            dialog.destroy()
        
        ttk.Button(dialog, text="Зберегти", command=submit).pack(pady=20)
        update_accounts()
    
    def remove_channel_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Видалити канал")
        dialog.geometry("600x600")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Ім'я користувача каналу для видалення:").pack(pady=5)
        channel_entry = ttk.Entry(dialog, width=40)
        channel_entry.pack(pady=5)
        
        def submit():
            channel = channel_entry.get().strip()
            if self.commenter.remove_channel(channel):
                self.show_message("Успіх", "✅ Канал видалено")
                self.log_message(f"Канал @{channel} видалено")
            else:
                self.show_message("Помилка", "⌐ Канал не знайдено", "warning")
            dialog.destroy()
        
        ttk.Button(dialog, text="Видалити", command=submit).pack(pady=20)
    
    def change_settings_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Змінити налаштування")
        dialog.geometry("700x500")
        dialog.transient(self.root)
        dialog.grab_set()
        
        settings = self.commenter.config["comment_settings"]
        
        notebook = ttk.Notebook(dialog)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        time_frame = ttk.Frame(notebook)
        notebook.add(time_frame, text="⏰ Час")
        
        ttk.Label(time_frame, text=f"Мінімальна затримка (хв): {settings['min_delay']}").pack(pady=5)
        min_delay_entry = ttk.Entry(time_frame, width=10)
        min_delay_entry.insert(0, settings['min_delay'])
        min_delay_entry.pack(pady=5)
        
        ttk.Label(time_frame, text=f"Максимальна затримка (хв): {settings['max_delay']}").pack(pady=5)
        max_delay_entry = ttk.Entry(time_frame, width=10)
        max_delay_entry.insert(0, settings['max_delay'])
        max_delay_entry.pack(pady=5)
        
        activity_frame = ttk.Frame(notebook)
        notebook.add(activity_frame, text="🎯 Активність")
        
        ttk.Label(activity_frame, text=f"Ймовірність коментаря (0-1): {settings['comment_probability']}").pack(pady=5)
        comment_prob_entry = ttk.Entry(activity_frame, width=10)
        comment_prob_entry.insert(0, settings['comment_probability'])
        comment_prob_entry.pack(pady=5)
        
        ttk.Label(activity_frame, text=f"Ймовірність лайка (0-1): {settings['like_probability']}").pack(pady=5)
        like_prob_entry = ttk.Entry(activity_frame, width=10)
        like_prob_entry.insert(0, settings['like_probability'])
        like_prob_entry.pack(pady=5)
        
        ttk.Label(activity_frame, text=f"Ймовірність лайка відповіді (0-1): {settings.get('reply_like_probability', 0.3)}").pack(pady=5)
        reply_like_prob_entry = ttk.Entry(activity_frame, width=10)
        reply_like_prob_entry.insert(0, settings.get('reply_like_probability', 0.3))
        reply_like_prob_entry.pack(pady=5)
        
        ttk.Label(activity_frame, text=f"Ймовірність тихої активності (0-1): {settings.get('silent_activity_probability', 0.2)}").pack(pady=5)
        silent_prob_entry = ttk.Entry(activity_frame, width=10)
        silent_prob_entry.insert(0, settings.get('silent_activity_probability', 0.2))
        silent_prob_entry.pack(pady=5)
        
        ttk.Label(activity_frame, text=f"Мінімум коментарів на пост: {settings.get('min_comments_per_post', 3)}").pack(pady=5)
        min_comments_entry = ttk.Entry(activity_frame, width=10)
        min_comments_entry.insert(0, settings.get('min_comments_per_post', 3))
        min_comments_entry.pack(pady=5)
        
        ttk.Label(activity_frame, text=f"Максимум коментарів на пост: {settings.get('max_comments_per_post', 8)}").pack(pady=5)
        max_comments_entry = ttk.Entry(activity_frame, width=10)
        max_comments_entry.insert(0, settings.get('max_comments_per_post', 8))
        max_comments_entry.pack(pady=5)
        
        def submit():
            try:
                min_delay = int(min_delay_entry.get() or settings['min_delay'])
                max_delay = int(max_delay_entry.get() or settings['max_delay'])
                if min_delay > max_delay:
                    raise ValueError("Мінімальна затримка не може перевищувати максимальну")
                
                comment_prob = float(comment_prob_entry.get() or settings['comment_probability'])
                like_prob = float(like_prob_entry.get() or settings['like_probability'])
                reply_like_prob = float(reply_like_prob_entry.get() or settings.get('reply_like_probability', 0.3))
                silent_prob = float(silent_prob_entry.get() or settings.get('silent_activity_probability', 0.2))
                min_comments = int(min_comments_entry.get() or settings.get('min_comments_per_post', 3))
                max_comments = int(max_comments_entry.get() or settings.get('max_comments_per_post', 8))
                
                if min_comments > max_comments:
                    raise ValueError("Мінімум коментарів не може перевищувати максимум")
                
                settings['min_delay'] = min_delay
                settings['max_delay'] = max_delay
                settings['comment_probability'] = comment_prob
                settings['like_probability'] = like_prob
                settings['reply_like_probability'] = reply_like_prob
                settings['silent_activity_probability'] = silent_prob
                settings['min_comments_per_post'] = min_comments
                settings['max_comments_per_post'] = max_comments
                
                self.commenter.save_config()
                self.show_message("Успіх", "✅ Налаштування збережено")
                self.log_message("Налаштування оновлено")
            except ValueError as e:
                self.show_message("Помилка", f"❌ Некоректний формат: {e}", "warning")
            dialog.destroy()
        
        ttk.Button(dialog, text="Зберегти", command=submit).pack(pady=20)
    
    def show_settings(self):
        settings = self.commenter.config
        msg = f"""📋 Поточні налаштування:
Облікові записи: {len(settings['accounts'])}
Канали: {len(settings['channels'])}
Затримка (випадковий діапазон): {settings['comment_settings']['min_delay']}-{settings['comment_settings']['max_delay']} хв
Ймовірність коментаря: {settings['comment_settings']['comment_probability']*100}% 
Ймовірність лайка: {settings['comment_settings']['like_probability']*100}% 
Ймовірність лайка відповіді: {settings['comment_settings'].get('reply_like_probability', 0.3)*100}% 
Ймовірність тихої активності: {settings['comment_settings'].get('silent_activity_probability', 0.2)*100}% 
AI генерація: {'✅ Увімкнено' if settings['ai_settings']['enabled'] else '⌐ Вимкнено'}"""
        self.show_message("Налаштування", msg)
    
    def show_statistics(self):
        stats = self.commenter.show_statistics_text()
        self.show_message("📊 Статистика", stats)
    
    def show_accounts_status(self):
        status = self.commenter.show_accounts_status_text()
        self.show_message("👥 Статус облікових записів", status)
    
    def show_channels_status(self):
        status = self.commenter.show_channels_status_text()
        self.show_message("📺 Статус каналів", status)
    
    def check_connections(self):
        if not self.commenter.config['accounts']:
            self.show_message("Помилка", "❌ Жодного облікового запису не додано", "warning")
            return
        
        def run_check():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                results = loop.run_until_complete(self.commenter.check_connections_gui(self.log_message))
                self.root.after(0, lambda: self.show_message("Результати перевірки", results))
            except Exception as e:
                self.log_message(f"Помилка перевірки: {e}")
            finally:
                loop.close()
        
        thread = threading.Thread(target=run_check, daemon=True)
        thread.start()
        self.log_message("🔍 Перевірка підключень...")
    
    def refresh_status(self):
        self.log_message("Статус оновлено")
    
    def start_bot(self):
        if not self.commenter.config['accounts']:
            self.show_message("Помилка", "❌ Жодного облікового запису не додано", "warning")
            return
        if not self.commenter.config['channels']:
            self.show_message("Помилка", "❌ Жодного каналу не додано", "warning")
            return
        
        if self.monitoring_active:
            self.show_message("Попередження", "Бот уже запущено", "warning")
            return
        
        auth_warning = """🚀 Запуск бота...

⚠️ ВАЖЛИВО:
- Якщо обліковий запис не авторизовано, з'являться діалоги для введення коду
- Переконайтеся, що коментарі увімкнено в каналах

Продовжити?"""
        
        if not messagebox.askyesno("Підтвердження запуску", auth_warning):
            return
        
        self.monitoring_active = True
        self.commenter.monitoring_active = True
        self.monitoring_thread = threading.Thread(target=self.run_monitoring, daemon=True)
        self.monitoring_thread.start()
        self.log_message("🚀 Бот запущено з випадковими затримками та ймовірностями")
    
    def stop_bot(self):
        if not self.monitoring_active:
            self.show_message("Попередження", "Бот не запущено", "warning")
            return
        
        self.monitoring_active = False
        self.commenter.monitoring_active = False
        
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.log_message("🛑 Зупинка бота...")
            self.monitoring_thread.join(timeout=5)
        
        self.show_message("Успіх", "🛑 Бот зупинено")
    
    def run_monitoring(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def monitor():
            try:
                await self.commenter.initialize_clients_gui(self.input_dialog, self.log_message)
                await self.commenter.start_monitoring_gui(self.log_message)
            except Exception as e:
                self.log_message(f"Помилка: {e}")
            finally:
                self.monitoring_active = False
                self.commenter.monitoring_active = False
        
        loop.run_until_complete(monitor())
        loop.close()

def main():
    root = tk.Tk()
    app = TelegramCommenterGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()