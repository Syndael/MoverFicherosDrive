from __future__ import print_function
import pickle
import os
import shutil
import configparser
import logging
import telebot
import urllib
import mimetypes
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from datetime import date
from httplib2 import Http
from oauth2client import client, file, tools
from apiclient.http import MediaFileUpload

SCOPES = ['https://www.googleapis.com/auth/drive.file']

driveService = None
configParser = None
extensionesPermitidas = None

def main():
    global extensionesPermitidas

    directorioMover = getConfigParserGet('directorio')
    extensionesPermitidas = getConfigParserGet('extensionesPermitidas')

    ficheroLog = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'mover.log')
    logging.basicConfig(filename=ficheroLog, filemode='a',
                        format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%d/%m/%Y %H:%M:%S', level=logging.INFO)

    if existeAlgoPendiente(directorioMover):
        moverFicherosPendientes(directorioMover)
    else:
        logging.info('No hay ficheros pendientes')

def moverFicherosPendientes(directorioMover):
    global extensionesPermitidas

    crearBackup = getBooleanConfig('crearBackup')
    rutaBackup = getConfigParserGet('rutaBackup')
    destinoGDriveSubcarpeta = getConfigParserGet('destinoGDriveSubcarpeta')
    destinoFichero = None

    for r, d, f in os.walk(directorioMover):
        for directorio in d:
            logging.debug(str("Buscando ficheros en " + directorio))
            moverFicherosPendientes(os.path.join(directorioMover, directorio))

        for fichero in f:
            if fichero.split(".")[-1] in str(extensionesPermitidas):
                if getConfigParserGet('modoCopia') == '1':
                    if not destinoFichero:
                        destinoFichero = generarEncontrarEstructura()
                    rutaCompleta = os.path.join(r, fichero)
                    urlFichero = subirFichero(destinoFichero, fichero,  rutaCompleta)
                    if crearBackup and rutaBackup:
                        logging.debug(str("Moviendo " + fichero + " a la carpeta " + rutaBackup))
                        shutil.move(rutaCompleta, rutaBackup)
                    else:
                        logging.debug(str("Eliminando el fichero de " + rutaCompleta))
                        os.remove(rutaCompleta)

                    enviarMensajeTelegram(fichero, urlFichero)
                elif getConfigParserGet('modoCopia') == '2':
                    destinoDefault = getConfigParserGet('destinoGDriveModo2Default')
                    rutaActual = r
                    estructuraBase = rutaActual.replace(getConfigParserGet('directorio'), '').split(getConfigParserGet('separador'))
                    carpetaRaiz = estructuraBase[1].replace('_', ' ')
                    carpetaDrive = buscarCarpetaDrive(carpetaRaiz)
                    if carpetaDrive:
                        logging.debug(str("carpetaDrive " + str(carpetaDrive)))
                    elif destinoDefault:
                        logging.warning(str("No se ha encontrado la carpeta " + carpetaRaiz + " se movera a la carpeta " + destinoDefault))
                        carpetaDrive = crearCarpetaDrive(carpetaRaiz, destinoDefault)
                    else:
                        carpetaDrive = None

                    if carpetaDrive:
                        estructuraBase.pop(0)
                        estructuraBase.pop(0)

                        destinoGDriveSubcarpetaSplit = destinoGDriveSubcarpeta.split(getConfigParserGet('separador'))
                        if len(destinoGDriveSubcarpetaSplit) != 0:
                            for dest in reversed(destinoGDriveSubcarpetaSplit):
                                estructuraBase.insert(0, dest)

                        logging.debug(str("Creando estructura " + str(estructuraBase)))
                        for dir in estructuraBase:
                            carpetaDrive = buscarCrearCarpetaDrive(str(dir), carpetaDrive)

                        rutaCompleta = os.path.join(r, fichero)
                        urlFichero = subirFichero(carpetaDrive, fichero,  rutaCompleta)
                        if crearBackup and rutaBackup:
                            logging.debug(str("Moviendo " + fichero + " a la carpeta " + rutaBackup))
                            shutil.move(rutaCompleta, rutaBackup)
                        else:
                            logging.debug(str("Eliminando el fichero de " + rutaCompleta))
                            os.remove(rutaCompleta)
                    else:
                        logging.error(str("No se ha encontrado la carpeta " + carpetaRaiz + " y no exite carpeta por defecto"))
        break

def existeAlgoPendiente(directorioMover):
    global extensionesPermitidas

    algoPendiente = False
    if directorioMover:
        for r, d, f in os.walk(directorioMover):
            for directorio in d:
                logging.debug(str("Buscando ficheros en " + directorio))
                algoPendiente = algoPendiente or existeAlgoPendiente(os.path.join(directorioMover, directorio))
                if algoPendiente:
                    break

            for fichero in f:
                extension = fichero.split(".")[-1]
                logging.debug(str("Comprobando el fichero " + fichero + " con extension " + extension + " contra " + str(extensionesPermitidas)))
                algoPendiente = algoPendiente or extension in str(extensionesPermitidas)
                if algoPendiente:
                    break
            break

    return algoPendiente

def generarEncontrarEstructura():
    destinoGDrive = getConfigParserGet('destinoGDrive')
    destinoGDriveSubcarpeta = getConfigParserGet('destinoGDriveSubcarpeta')

    destinoFichero = destinoGDrive
    if destinoGDriveSubcarpeta:
        destinoFichero = buscarCrearCarpetaDrive(destinoGDriveSubcarpeta, destinoGDrive)

    fechaActual = date.today()
    destinoFichero = buscarCrearCarpetaDrive(str(fechaActual.year), destinoFichero)
    destinoFichero = buscarCrearCarpetaDrive(str(fechaActual.month), destinoFichero)
    destinoFichero = buscarCrearCarpetaDrive(str(fechaActual.day), destinoFichero)

    return destinoFichero

def getBooleanConfig(clave):
    aux = getConfigParserGet(clave)
    if aux == 'True' or aux == '1':
        return True
    elif aux == 'False' or aux == '0':
        return False
    else:
        return None

def getConfigParserGet(clave):
    return getConfigParser().get('config', clave)


def getConfigParser():
    global configParser
    if configParser is None:
        configParser = configparser.RawConfigParser()
        ficheroConfig = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'config.txt')
        configParser.read(ficheroConfig)

    return configParser


def getDriveService():
    global driveService
    if driveService is None:
        rutaCreedenciales = getConfigParserGet('rutaCreedenciales')
        clienteSecreto = getConfigParserGet('clienteSecreto')
        store = file.Storage(rutaCreedenciales)
        creds = store.get()
        if not creds or creds.invalid:
            flow = client.flow_from_clientsecrets(clienteSecreto, SCOPES)
            creds = tools.run_flow(flow, store)
        driveService = build('drive', 'v3', cache_discovery=False, http=creds.authorize(Http()))

    return driveService


def subirFichero(carpetaDestinoId, fichero, rutaCompleta):
    metadata = {'title': fichero, 'name': fichero, 'parents': [carpetaDestinoId]}
    logging.info(metadata)
    logging.info(str("Subiendo fichero " + fichero + " a la carpeta " + carpetaDestinoId))

    media = MediaFileUpload(rutaCompleta, mimetype=mimetypes.guess_type(fichero)[0])
    destino = getDriveService().files().create(body=metadata, media_body=media, fields='id').execute()
    logging.info("Fichero subido correctamente")

    compartirGDrive = getBooleanConfig('compartirGDrive')
    if compartirGDrive:
        getDriveService().permissions().create(
            body={"role": "reader", "type": "anyone"}, fileId=destino['id']).execute()
    ficheroGdrive = getDriveService().files().get(
        fileId=destino['id'], fields="webContentLink").execute()
    return ficheroGdrive['webContentLink']


def buscarCarpetaDrive(folderName = None, parentId = None):
    try:
        if folderName:
            page_token = None
            while True:
                if(parentId):
                    logging.info(str("Buscando la carpeta " + folderName +
                                     " en drive dentro de " + parentId))
                    response = getDriveService().files().list(q='(mimeType = \'application/vnd.google-apps.folder\') and (name = \'' + folderName + '\') and (trashed = false) and (\'' +
                                                              parentId + '\' in parents)', spaces='drive', fields='nextPageToken, files(id, name)', pageToken=page_token).execute()
                else:
                    response = getDriveService().files().list(q='(mimeType = \'application/vnd.google-apps.folder\') and (name = \'' + folderName +
                                                              '\') and (trashed = false)', spaces='drive', fields='nextPageToken, files(id, name)', pageToken=page_token).execute()
                for file in response.get('files', []):
                    idCarpeta = file.get('id')
                    logging.info(str(
                        "Se ha encontrado carpeta en drive(id=" + idCarpeta + ") llamada " + folderName))
                    return idCarpeta
                page_token = response.get('nextPageToken', None)
                if page_token is None:
                    break
            logging.info(str("No se ha encontrado carpeta en drive con nombre " + folderName))
        return ''
    except Exception as ex:
        logging.error(str("Se ha producido un error al buscar la carpeta " + folderName + " en GDrive: " + str(ex)))
        return None


def crearCarpetaDrive(folderName, parentId = None):
    try:
        body = {
            'name': folderName,
            'mimeType': "application/vnd.google-apps.folder"
        }
        if parentId:
            logging.info(str("Se creara una carpeta en drive dentro de " + parentId))
            body['parents'] = [parentId]
        root_folder = getDriveService().files().create(body=body).execute()
        idCarpeta = root_folder['id']
        logging.info(str(
            "Se ha creado una carpeta en drive(id=" + idCarpeta + ")"))
        compartirGDrive = getConfigParserGet('compartirGDrive')
        if (compartirGDrive):
            getDriveService().permissions().create(
                body={"role": "reader", "type": "anyone"}, fileId=idCarpeta).execute()
        return idCarpeta
    except Exception as ex:
        logging.error(str(
            "Caught an exception in crearCarpetaDrive(): " + str(ex)))


def buscarCrearCarpetaDrive(folderName, parentId=None):
    logging.info(str("Carpeta en drive id: " + parentId))
    carpetaEncontrada = buscarCarpetaDrive(folderName, parentId)
    if carpetaEncontrada == '':
        carpetaEncontrada = crearCarpetaDrive(folderName, parentId)
    return carpetaEncontrada


def enviarMensajeTelegram(nombreFichero, urlFichero):
    telegramBotToken = getConfigParserGet('telegramBotToken')
    telegramChatId = getConfigParserGet('telegramChatId')
    telegramMensaje = getConfigParserGet('telegramMensaje')
    if(telegramBotToken and telegramChatId):
        telegramService = telebot.TeleBot(telegramBotToken)
        mensaje = 'OK'
        if(telegramMensaje):
            nombreFichero = nombreFichero.split(".")[0]
            mensaje = telegramMensaje.replace('[file]', nombreFichero).replace('[url]', urlFichero)

        telegramService.send_message(telegramChatId, mensaje)


if __name__ == '__main__':
    main()
