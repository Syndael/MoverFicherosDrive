from __future__ import print_function
import pickle
import os
import shutil
import ConfigParser
import logging
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from datetime import date
from httplib2 import Http
from oauth2client import client, file, tools

SCOPES = ['https://www.googleapis.com/auth/drive.file']

driveService = None
configParser = None


def main():
    directorioMover = getConfigParserGet('directorio')
    rutaBackup = getConfigParserGet('rutaBackup')
    extensionesPermitidas = getConfigParserGet('extensionesPermitidas')

    logging.basicConfig(filename='mover.log', filemode='a',
                        format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%d/%m/%Y %H:%M:%S', level=logging.INFO)

    algoPendiente = False
    for r, d, f in os.walk(directorioMover):
        for fichero in f:
            algoPendiente = algoPendiente or fichero.split(
                ".")[-1] in str(extensionesPermitidas)
        break

    if algoPendiente:
        destinoFichero = generarEncontrarEstructura()
        for r, d, f in os.walk(directorioMover):
            for fichero in f:
                if fichero.split(".")[-1] in str(extensionesPermitidas):
                    rutaCompleta = os.path.join(r, fichero)
                    subirFichero(destinoFichero, fichero,  rutaCompleta)
                    if rutaBackup:
                        logging.info(str("Moviendo " + fichero + " a la carpeta " + rutaBackup))
                        shutil.move(rutaCompleta, rutaBackup)
            break
    else:
        logging.info('No hay ficheros pendientes')


def generarEncontrarEstructura():
    destinoGDrive = getConfigParserGet('destinoGDrive')
    destinoGDriveSubcarpeta = getConfigParserGet('destinoGDriveSubcarpeta')

    destinoFichero = destinoGDrive
    if destinoGDriveSubcarpeta:
        destinoFichero = buscarCrearCarpetaDrive(
            destinoGDriveSubcarpeta, destinoGDrive)

    fechaActual = date.today()
    destinoFichero = buscarCrearCarpetaDrive(
        str(fechaActual.year), destinoFichero)
    destinoFichero = buscarCrearCarpetaDrive(
        str(fechaActual.month), destinoFichero)
    destinoFichero = buscarCrearCarpetaDrive(
        str(fechaActual.day), destinoFichero)

    return destinoFichero


def getConfigParserGet(clave):
    return getConfigParser().get('config', clave)


def getConfigParser():
    global configParser
    if configParser is None:
        configParser = ConfigParser.RawConfigParser()
        ficheroConfig = os.path.join(os.path.abspath(
            os.path.dirname(__file__)), 'config.txt')
        configParser.read(ficheroConfig)

    return configParser


def getDriveService():
    global driveService
    if driveService is None:
        rutaCreedenciales = getConfigParser().get('config', 'rutaCreedenciales')
        clienteSecreto = getConfigParser().get('config', 'clienteSecreto')
        store = file.Storage(rutaCreedenciales)
        creds = store.get()
        if not creds or creds.invalid:
            flow = client.flow_from_clientsecrets(clienteSecreto, SCOPES)
            creds = tools.run_flow(flow, store)
        driveService = build(
            'drive', 'v3', cache_discovery=False, http=creds.authorize(Http()))

    return driveService


def subirFichero(carpetaDestinoId, fichero, rutaCompleta):
    metadata = {'title': fichero, 'name': fichero,
                'parents': [carpetaDestinoId]}
    logging.info(str("Subiendo fichero " + fichero + " a la carpeta " + carpetaDestinoId))
    destino = getDriveService().files().create(
        body=metadata, media_body=rutaCompleta, fields='id').execute()
    logging.info("Fichero subido correctamente")


def buscarCarpetaDrive(folder_name='', parentID=None):
    try:
        if folder_name != '':
            page_token = None
            while True:
                if(parentID):
                    logging.info(str("Buscando la carpeta " + folder_name +
                                     " en drive dentro de " + parentID))
                    response = getDriveService().files().list(q='(mimeType = \'application/vnd.google-apps.folder\') and (name = \'' + folder_name + '\') and (trashed = false) and (\'' +
                                                              parentID + '\' in parents)', spaces='drive', fields='nextPageToken, files(id, name)', pageToken=page_token).execute()
                else:
                    response = getDriveService().files().list(q='(mimeType = \'application/vnd.google-apps.folder\') and (name = \'' + folder_name +
                                                              '\') and (trashed = false)', spaces='drive', fields='nextPageToken, files(id, name)', pageToken=page_token).execute()
                for file in response.get('files', []):
                    idCarpeta = file.get('id')
                    logging.info(str(
                        "Se ha encontrado carpeta en drive(id=" + idCarpeta + ") llamada " + folder_name))
                    return idCarpeta
                page_token = response.get('nextPageToken', None)
                if page_token is None:
                    break
            logging.info(str("No se ha encontrado carpeta en drive con nombre " + folder_name))
        return ''
    except Exception as ex:
        logging.error(str("Se ha producido un error al buscar la carpeta ",
                          folder_name + " en GDrive: " + str(ex)))
        return None


def crearCarpetaDrive(folderName, parentID=None, compartir=None):
    try:
        body = {
            'name': folderName,
            'mimeType': "application/vnd.google-apps.folder"
        }
        if parentID:
            logging.info(str("Se creara una carpeta en drive dentro de " + parentID))
            body['parents'] = [parentID]
        root_folder = getDriveService().files().create(body=body).execute()
        idCarpeta = root_folder['id']
        logging.info(str(
            "Se ha creado una carpeta en drive(id=" + idCarpeta + ")"))
        if (compartir):
            getDriveService().permissions().create(
                body={"role": "reader", "type": "anyone"}, fileId=idCarpeta).execute()
        return idCarpeta
    except Exception as ex:
        logging.error(str(
            "Caught an exception in crearCarpetaDrive(): " + str(ex)))


def buscarCrearCarpetaDrive(folderName, parentID=None, compartir=None):
    logging.info(str("Carpeta en drive id: " + parentID))
    carpetaEncontrada = buscarCarpetaDrive(folderName, parentID)
    if carpetaEncontrada == '':
        carpetaEncontrada = crearCarpetaDrive(
            folderName, parentID, compartir)
    return carpetaEncontrada


if __name__ == '__main__':
    main()
