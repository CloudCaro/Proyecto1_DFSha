import os
import shlex

from client.commands import CommandManager


NAMENODE_URL = os.getenv(
    "NAMENODE_URL",
    "http://localhost:8000"
)


def print_result(result):

    if isinstance(result, dict):

        for key, value in result.items():
            print(f"{key}: {value}")

    else:
        print(result)


def main():

    client = CommandManager(
        NAMENODE_URL
    )

    print("=" * 45)
    print("          DFSha - Distributed File System")
    print("=" * 45)

    print(f"Namenode: {NAMENODE_URL}")
    print("Escribe 'help' para consultar los comandos.")

    while True:

        try:

            command = input("\nDFSha> ").strip()

            if not command:
                continue

            args = shlex.split(command)

            action = args[0].lower()

            if action == "exit":
                break

            elif action == "help":

                print("""
COMANDOS DFSha

register <usuario> <contraseña>
login <usuario> <contraseña>
logout

ls
cd <nombre|..|/>
mkdir <nombre>
rmdir <directory_id>

put <ruta_local>
get <file_id> [destino]
rm <file_id>

open <file_id> <r|w>
lock
unlock
write <ruta_local>
read [offset] [length]
close

exit
""")

            elif action == "register":

                result = client.register(
                    args[1],
                    args[2]
                )

                print_result(result)

            elif action == "login":

                result = client.login(
                    args[1],
                    args[2]
                )

                print(
                    f"Sesión iniciada: {result['username']}"
                )

            elif action == "logout":

                client.logout()

                print("Sesión cerrada.")

            elif action == "ls":

                result = client.ls()

                print_result(result)

            elif action == "cd":

                result = client.cd(args[1])
                print_result(result)

            elif action == "mkdir":

                result = client.mkdir(
                    args[1]
                )

                print_result(result)

            elif action == "rmdir":

                result = client.rmdir(
                    int(args[1])
                )

                print_result(result)

            elif action == "put":

                result = client.put(
                    args[1]
                )

                print_result(result)

            elif action == "get":

                destination = (
                    args[2] if len(args) > 2 else "."
                )

                result = client.get(
                    int(args[1]),
                    destination
                )

                print(f"Archivo descargado en: {result}")

            elif action == "rm":

                result = client.rm(
                    int(args[1])
                )

                print_result(result)

            elif action == "open":

                result = client.open(
                    int(args[1]),
                    args[2]
                )

                print_result(result)

            elif action == "lock":

                result = client.lock()

                print_result(result)

            elif action == "unlock":

                result = client.unlock()

                print_result(result)

            elif action == "write":

                result = client.write(
                    args[1]
                )

                print_result(result)

            elif action == "read":

                offset = int(args[1]) if len(args) > 1 else 0
                length = int(args[2]) if len(args) > 2 else 4096

                content = client.read(
                    offset,
                    length
                )

                print(content.decode("utf-8", errors="replace"))

            elif action == "close":

                result = client.close()

                print_result(result)

            else:

                print(
                    "Comando desconocido. Escribe 'help'."
                )

        except IndexError:

            print(
                "Faltan argumentos. Escribe 'help' para consultar el uso."
            )

        except Exception as error:

            print(f"Error: {error}")

    print("\nDFSha finalizado.")


if __name__ == "__main__":
    main()