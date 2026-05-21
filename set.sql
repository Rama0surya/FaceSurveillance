CREATE USER 'nvruser'@'localhost' IDENTIFIED BY 'user123';
CREATE DATABASE IF NOT EXISTS face_surveillance;
GRANT ALL PRIVILEGES ON face_surveillance.* TO 'nvruser'@'localhost';
FLUSH PRIVILEGES;