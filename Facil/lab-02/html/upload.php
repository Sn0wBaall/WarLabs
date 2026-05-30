<?php

if (isset($_FILES['file'])) {
    $target = "uploads/" . $_FILES['file']['name'];
    move_uploaded_file($_FILES['file']['tmp_name'], $target);
}

header("Location: index.php");
exit;

?>

