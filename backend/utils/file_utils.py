import os
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
import hashlib
from datetime import datetime
from loguru import logger

class FileUtils:
    """Utilidades para manejo de archivos en el sistema legal"""
    
    def __init__(self):
        self.supported_formats = ['.pdf', '.doc', '.docx', '.txt']
        self.max_file_size = 50 * 1024 * 1024  # 50MB
    
    def validate_file(self, file_path: str) -> Dict[str, Any]:
        """
        Valida un archivo para procesamiento
        
        Args:
            file_path: Ruta al archivo
            
        Returns:
            Dict con resultado de validación
        """
        
        path = Path(file_path)
        
        validation_result = {
            "is_valid": True,
            "issues": [],
            "file_info": {}
        }
        
        # Verificar que existe
        if not path.exists():
            validation_result["is_valid"] = False
            validation_result["issues"].append("Archivo no encontrado")
            return validation_result
        
        # Verificar formato
        if path.suffix.lower() not in self.supported_formats:
            validation_result["is_valid"] = False
            validation_result["issues"].append(f"Formato no soportado: {path.suffix}")
        
        # Verificar tamaño
        file_size = path.stat().st_size
        if file_size > self.max_file_size:
            validation_result["is_valid"] = False
            validation_result["issues"].append(f"Archivo demasiado grande: {file_size / (1024*1024):.1f}MB")
        
        # Verificar que no esté corrupto (básico)
        try:
            with open(path, 'rb') as f:
                f.read(1024)  # Intentar leer primeros 1KB
        except Exception as e:
            validation_result["is_valid"] = False
            validation_result["issues"].append(f"Archivo corrupto o ilegible: {str(e)}")
        
        # Información del archivo
        validation_result["file_info"] = {
            "name": path.name,
            "size": file_size,
            "size_mb": file_size / (1024*1024),
            "format": path.suffix.lower(),
            "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat()
        }
        
        return validation_result
    
    def get_file_hash(self, file_path: str) -> str:
        """
        Calcula hash MD5 de un archivo
        
        Args:
            file_path: Ruta al archivo
            
        Returns:
            Hash MD5 del archivo
        """
        
        hash_md5 = hashlib.md5()
        
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            logger.error(f"Error calculando hash de {file_path}: {str(e)}")
            return ""
    
    def organize_files_by_type(self, source_dir: str, target_dir: str) -> Dict[str, Any]:
        """
        Organiza archivos por tipo en subdirectorios
        
        Args:
            source_dir: Directorio origen
            target_dir: Directorio destino
            
        Returns:
            Dict con resultados de la organización
        """
        
        source_path = Path(source_dir)
        target_path = Path(target_dir)
        
        # Crear subdirectorios por tipo
        type_dirs = {}
        for format_ext in self.supported_formats:
            type_dir = target_path / format_ext[1:].lower()  # Quitar el punto
            type_dir.mkdir(parents=True, exist_ok=True)
            type_dirs[format_ext] = type_dir
        
        results = {
            "organized": 0,
            "failed": 0,
            "details": []
        }
        
        # Organizar archivos
        for file_path in source_path.glob("*"):
            if file_path.is_file():
                try:
                    format_ext = file_path.suffix.lower()
                    
                    if format_ext in type_dirs:
                        target_file = type_dirs[format_ext] / file_path.name
                        
                        # Evitar sobrescribir
                        counter = 1
                        while target_file.exists():
                            stem = file_path.stem
                            target_file = type_dirs[format_ext] / f"{stem}_{counter}{format_ext}"
                            counter += 1
                        
                        shutil.move(str(file_path), str(target_file))
                        results["organized"] += 1
                        results["details"].append(f"Movido: {file_path.name} → {type_dirs[format_ext].name}")
                        
                    else:
                        results["failed"] += 1
                        results["details"].append(f"Formato no soportado: {file_path.name}")
                        
                except Exception as e:
                    results["failed"] += 1
                    results["details"].append(f"Error moviendo {file_path.name}: {str(e)}")
        
        return results
    
    def find_duplicate_files(self, directory: str) -> Dict[str, List[str]]:
        """
        Encuentra archivos duplicados por hash
        
        Args:
            directory: Directorio a analizar
            
        Returns:
            Dict con grupos de archivos duplicados
        """
        
        dir_path = Path(directory)
        hash_groups = {}
        
        # Calcular hash de cada archivo
        for file_path in dir_path.rglob("*"):
            if file_path.is_file():
                try:
                    file_hash = self.get_file_hash(str(file_path))
                    if file_hash:
                        if file_hash not in hash_groups:
                            hash_groups[file_hash] = []
                        hash_groups[file_hash].append(str(file_path))
                except Exception as e:
                    logger.warning(f"Error procesando {file_path}: {str(e)}")
        
        # Filtrar solo duplicados
        duplicates = {
            hash_val: files 
            for hash_val, files in hash_groups.items() 
            if len(files) > 1
        }
        
        return duplicates
    
    def clean_empty_directories(self, directory: str) -> Dict[str, Any]:
        """
        Elimina directorios vacíos
        
        Args:
            directory: Directorio a limpiar
            
        Returns:
            Dict con resultados de la limpieza
        """
        
        dir_path = Path(directory)
        removed_dirs = []
        
        # Recorrer de abajo hacia arriba
        for root, dirs, files in os.walk(directory, topdown=False):
            for dir_name in dirs:
                dir_full_path = Path(root) / dir_name
                
                try:
                    # Verificar si está vacío
                    if not any(dir_full_path.iterdir()):
                        dir_full_path.rmdir()
                        removed_dirs.append(str(dir_full_path))
                except OSError:
                    # Directorio no está vacío o no se puede eliminar
                    pass
        
        return {
            "removed_count": len(removed_dirs),
            "removed_directories": removed_dirs
        }
    
    def get_directory_stats(self, directory: str) -> Dict[str, Any]:
        """
        Obtiene estadísticas de un directorio
        
        Args:
            directory: Directorio a analizar
            
        Returns:
            Dict con estadísticas
        """
        
        dir_path = Path(directory)
        
        stats = {
            "total_files": 0,
            "total_size": 0,
            "file_types": {},
            "largest_files": [],
            "recent_files": []
        }
        
        all_files = []
        
        # Analizar archivos
        for file_path in dir_path.rglob("*"):
            if file_path.is_file():
                try:
                    file_size = file_path.stat().st_size
                    file_ext = file_path.suffix.lower()
                    modified_time = file_path.stat().st_mtime
                    
                    stats["total_files"] += 1
                    stats["total_size"] += file_size
                    
                    # Contar por tipo
                    if file_ext not in stats["file_types"]:
                        stats["file_types"][file_ext] = {"count": 0, "size": 0}
                    stats["file_types"][file_ext]["count"] += 1
                    stats["file_types"][file_ext]["size"] += file_size
                    
                    # Guardar información para análisis
                    all_files.append({
                        "path": str(file_path),
                        "name": file_path.name,
                        "size": file_size,
                        "ext": file_ext,
                        "modified": modified_time
                    })
                    
                except Exception as e:
                    logger.warning(f"Error analizando {file_path}: {str(e)}")
        
        # Ordenar y limitar resultados
        stats["largest_files"] = sorted(
            all_files, 
            key=lambda x: x["size"], 
            reverse=True
        )[:10]
        
        stats["recent_files"] = sorted(
            all_files, 
            key=lambda x: x["modified"], 
            reverse=True
        )[:10]
        
        # Formatear tamaño total
        stats["total_size_mb"] = stats["total_size"] / (1024 * 1024)
        stats["total_size_gb"] = stats["total_size"] / (1024 * 1024 * 1024)
        
        return stats
    
    def backup_directory(self, source_dir: str, backup_dir: str) -> Dict[str, Any]:
        """
        Crea copia de seguridad de un directorio
        
        Args:
            source_dir: Directorio origen
            backup_dir: Directorio destino
            
        Returns:
            Dict con resultados del backup
        """
        
        source_path = Path(source_dir)
        backup_path = Path(backup_dir)
        
        # Crear nombre con timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{timestamp}"
        backup_full_path = backup_path / backup_name
        
        try:
            # Crear backup
            shutil.copytree(source_path, backup_full_path)
            
            # Obtener estadísticas
            stats = self.get_directory_stats(str(backup_full_path))
            
            return {
                "success": True,
                "backup_path": str(backup_full_path),
                "timestamp": timestamp,
                "stats": stats
            }
            
        except Exception as e:
            logger.error(f"Error creando backup: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def restore_from_backup(self, backup_path: str, target_dir: str) -> Dict[str, Any]:
        """
        Restaura desde backup
        
        Args:
            backup_path: Directorio de backup
            target_dir: Directorio destino
            
        Returns:
            Dict con resultados de la restauración
        """
        
        backup = Path(backup_path)
        target = Path(target_dir)
        
        try:
            # Crear backup de seguridad del actual
            if target.exists():
                safety_backup = target.parent / f"safety_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.move(str(target), str(safety_backup))
            
            # Restaurar desde backup
            shutil.copytree(backup, target)
            
            return {
                "success": True,
                "restored_to": str(target),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error restaurando backup: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def compress_directory(self, directory: str, output_file: str) -> Dict[str, Any]:
        """
        Comprime un directorio en ZIP
        
        Args:
            directory: Directorio a comprimir
            output_file: Archivo ZIP de salida
            
        Returns:
            Dict con resultados de la compresión
        """
        
        import zipfile
        
        dir_path = Path(directory)
        output_path = Path(output_file)
        
        try:
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in dir_path.rglob("*"):
                    if file_path.is_file():
                        arcname = file_path.relative_to(dir_path)
                        zipf.write(file_path, arcname)
            
            # Obtener tamaño del archivo
            compressed_size = output_path.stat().st_size
            original_size = sum(f.stat().st_size for f in dir_path.rglob("*") if f.is_file())
            
            compression_ratio = (1 - compressed_size / original_size) * 100
            
            return {
                "success": True,
                "output_file": str(output_path),
                "original_size": original_size,
                "compressed_size": compressed_size,
                "compression_ratio": compression_ratio
            }
            
        except Exception as e:
            logger.error(f"Error comprimiendo directorio: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
