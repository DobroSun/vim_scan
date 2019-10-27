#!/usr/bin/env python3

import queue
import os
import re
import sqlite3
import sys
import subprocess
import tempfile
import threading as thr
import multiprocessing as mp

class HandlerThread(thr.Thread):
    def __init__(self, buf_q, send_q):
        super().__init__()
        self.buf_q = buf_q
        self.send_q = send_q
        self._running = True

    def run(self):
        while self._running:
            # Will wait for any object in queue
            name = self.send_q.get()


            msg = self.get_from_db(name)
            buf_q.put(msg)

    def get_from_db(self, name):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        for row in cursor.execute(f"""SELECT * FROM defs WHERE row LIKE '%{name}%'"""):
            print(row)
        #self.terminate()


    def terminate(self):
        self._running = False

class CallerThread(thr.Thread):
    def __init__(self, work_q, lock):
        super().__init__()
        self.work_q = work_q
        self.lock = lock
        self.threads = []


    def run(self):
        proc = subprocess.Popen(["find * -type f"], shell=True, stdout=subprocess.PIPE)
        filenames = proc.communicate()[0].decode().split("\n")
        
        self.exclude_ignored_files(filenames)
        print("Before waiting", filenames, sep=": ")

        th = thr.Thread(target=lambda proc: proc.wait(), args=(proc,))
        
        for file in filenames:
            if file == "" or file == DB_NAME:
                continue
            self.work_q.put(file)

        running_workers = []
        nthreads = len(filenames) if len(filenames) < 17 else 16
        for i in range(nthreads):
            th = WorkerThread(self.lock, self.work_q)
            th.start()

    def exclude_ignored_files(self, filenames):
        ignored = ".gitignore"
        if not os.path.isfile(ignored):
            return

        with open(ignored) as f:
            for pattern in f.read().split("\n"):
                if pattern == '':
                    continue
                for file in filenames:
                    if re.search(pattern, file):
                        try:
                            filenames.remove(file)
                        except:
                            pass

class WorkerThread(thr.Thread):
    PY_RE = [r"\w* = .*", r"def \w*(.*):", r"class \w*(.*):"]

    def __init__(self, lock, work_q):
        super().__init__()
        self.lock = lock
        self.work_q = work_q
        self._running = True
        self.connected = False
        self.conn = None
        self.cursor = None

    def parse_file(self, filename):
        with open(filename, "r") as f:
            for i, line in enumerate(f.read().split("\n")):
                for pattern in self.PY_RE:
                    compiled_p = re.compile(pattern)
                    res = re.search(compiled_p, line)
                    if not res or res.start() not in [0, 4]:
                        continue

                    self.push_to_db((filename, i+1, res.group(0)))

    def push_to_db(self, values):
        def _create_conn():
            self.conn = sqlite3.connect(DB_NAME)
            self.cursor = self.conn.cursor()

        if not self.connected:
            _create_conn()
            self.connected = True


        self.cursor.executemany("""INSERT INTO defs VALUES (?, ?, ?)""", [values])
        with self.lock:
            self.conn.commit()

    def run(self):
        while self._running:
            try:
                task = self.work_q.get_nowait()
                
                self.parse_file(task)
                self.work_q.task_done()
            except queue.Empty:
                print("Terminating")
                self.terminate()
    
    def terminate(self):
        self._running = False

def print_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    for row in cursor.execute("""SELECT * FROM defs"""):
        print(row)

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""DELETE FROM defs""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS defs (filename text, line int, row text)""")

    conn.commit()
    conn.close()

DB_NAME = "w.db"

def main():
    db_lock = thr.Lock()
    work_q, buf_q, send_q = queue.Queue(), queue.Queue(), queue.Queue()

    h = HandlerThread(buf_q, send_q)
    h.daemon = True
    h.start()

    caller = CallerThread(work_q, db_lock)
    caller.start()

    caller.join()


if __name__ == "__main__":
    init_db()
    prc = thr.Thread(target=main, args=())
    prc.start()

    a = 1
    for i in range(20):
        a += a * a

    prc.join()
    print_db()
