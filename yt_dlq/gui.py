import PySimpleGUI as sg


def input_popup(msg, default_input="", window_title="Input Required", beep=True):
    """
    PySimpleGUI window equivalent of input()
    """
    layout = [
        [sg.Text(msg)],
        [sg.InputText(key="-IN-", default_text=default_input, size=(80))],
        [sg.Submit()],
    ]
    if beep:
        print("\a")
    window = sg.Window(window_title, layout, modal=True)
    _, values = window.read()
    window.close()
    return values["-IN-"]
