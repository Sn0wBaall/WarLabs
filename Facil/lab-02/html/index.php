<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>S4rnL4bs | File Manager</title>
    <style>
        body {
            font-family: Arial, Helvetica, sans-serif;
            background-color: #0f0f0f;
            color: #e0e0e0;
        }
        .container {
            width: 600px;
            margin: 80px auto;
            padding: 20px;
            background-color: #1a1a1a;
            border-radius: 6px;
        }
        h1 {
            color: #7CFC00;
        }
        input[type="file"] {
            margin-top: 10px;
        }
        input[type="submit"] {
            margin-top: 15px;
            padding: 8px 16px;
            background-color: #7CFC00;
            border: none;
            cursor: pointer;
            font-weight: bold;
        }
        .footer {
            margin-top: 20px;
            font-size: 12px;
            color: #888;
        }
    </style>
</head>
<body>

<div class="container">
    <h1>Internal File Manager</h1>

    <p>
        Bienvenido al gestor interno de archivos.  
        Este sistema permite subir documentos al servidor para su posterior revisión.
    </p>

    <form action="upload.php" method="POST" enctype="multipart/form-data">
        <label>Selecciona un archivo:</label><br>
        <input type="file" name="file" required><br>
        <input type="submit" value="Subir archivo">
    </form>

    <div class="footer">
        <p>S4rnL4bs - Internal use only</p>
    </div>
</div>

</body>
</html>

