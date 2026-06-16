# -*- coding: utf-8 -*-

import time
from global_vars import processed_hosts, total_hosts

total_items = 100  # Gesamtanzahl der zu verarbeitenden Elemente
start_time = time.time()
remaining_time = 0
estimated_total_time = 0


def test():
    for i in range(total_items):
        # Simuliere eine Verarbeitungszeit (z. B. 0.1 Sekunde pro Element)
        time.sleep(0.5)

        # Aktuelle Zeit und Fortschritt berechnen
        elapsed_time = time.time() - start_time
        progress = (i + 1) / total_items
        estimated_total_time1 = elapsed_time / progress
        remaining_time1 = estimated_total_time1 - elapsed_time


        # Formatierung der Zeit in Minuten und Sekunden
        def format_time(seconds):
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins:02d}:{secs:02d}"


        # Ausgabe der Zeiten
        print(
            f"Fortschritt: {i + 1}/{total_items} | "
            f"Verstrichen: {format_time(elapsed_time)} | "
            f"Verbleibend: {format_time(remaining_time1)}",
            # end="\r"  # Überschreibt die vorherige Ausgabe
        )

    # Abschlussnachricht
    print("\nVerarbeitung abgeschlossen!")

def test2():
    global start_time, remaining_time, estimated_total_time
    start_time = time.time()

    elapsed_time = time.time() - start_time
    progress = ( + 1) / total_hosts
    estimated_total_time = elapsed_time / progress
    remaining_time = estimated_total_time - elapsed_time

    def format_time(seconds):
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"

    return format_time(estimated_total_time), format_time(remaining_time)

print(total_hosts, processed_hosts)
print(test2()[0])
print(test2()[1])