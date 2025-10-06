import importlib.util, sys, yaml
from pathlib import Path
from typing import List, Tuple, Type
from core.plugins.meta import PluginMeta
from core.plugins.interfaces import IPlugin

REQUIRED_KEYS = [
    "id", "name", "category", "subcategory", "version",
    "icon", "logic_class", "ui_class"
]

def _ensure_root_on_path() -> None:
    """
    Añade el root del proyecto a sys.path para que imports como `interfaces`
    funcionen cuando cargamos módulos por ruta.
    """
    root = Path(__file__).resolve().parents[2]  # .../gamma-lab-desktop-app
    sroot = str(root)
    if sroot not in sys.path:
        sys.path.insert(0, sroot)

def _load_meta(folder: Path) -> PluginMeta:
    yml = folder / "properties.yml"
    if not yml.exists():
        raise FileNotFoundError(str(yml))
    data = yaml.safe_load(yml.read_text(encoding="utf-8")) or {}
    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        raise ValueError(f"{folder.name}: faltan {missing} en properties.yml")
    meta = PluginMeta(**data)
    meta.root = folder
    return meta

def _import_class_from_dir(dirpath: Path, class_name: str) -> Type[IPlugin]:
    """
    Busca la clase `class_name` dentro de la carpeta del plugin sin asumir
    el nombre del archivo. Prioriza `plugin.py` y luego prueba cualquier .py.
    """
    _ensure_root_on_path()

    candidates: List[Path] = []
    # 1) Prioridad: plugin.py si existe
    if (dirpath / "plugin.py").exists():
        candidates.append(dirpath / "plugin.py")
    # 2) Cualquier otro .py de la carpeta (excepto __init__.py)
    for p in dirpath.glob("*.py"):
        if p.name in ("plugin.py", "__init__.py"):
            continue
        candidates.append(p)

    last_err = None
    for pyfile in candidates:
        try:
            # nombre de módulo único para evitar colisiones
            mod_name = f"plg_{dirpath.name}_{pyfile.stem}"
            spec = importlib.util.spec_from_file_location(mod_name, pyfile)
            if not spec or not spec.loader:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)  # type: ignore
            cls = getattr(module, class_name, None)
            if cls is not None:
                return cls
        except Exception as e:
            last_err = e
            continue

    raise ImportError(f"No se encontró la clase '{class_name}' en {dirpath} (último err: {last_err})")

def discover(plugins_root: Path) -> List[Tuple[PluginMeta, Type[IPlugin]]]:
    """
    Recorre recursivamente el árbol de `plugins_root` y considera plugin
    a toda carpeta que contenga un `properties.yml`.
    """
    results: List[Tuple[PluginMeta, Type[IPlugin]]] = []

    # Buscar *todas* las definiciones de plugin
    for yml in plugins_root.rglob("properties.yml"):
        folder = yml.parent
        # Ignorar carpetas basura
        if any(part == "__pycache__" for part in folder.parts):
            continue
        try:
            meta = _load_meta(folder)
            PluginCls = _import_class_from_dir(folder, meta.logic_class)
            results.append((meta, PluginCls))
        except Exception as e:
            print(f"[PLUGIN] {folder.relative_to(plugins_root)} omitido: {e}")
            continue

    return results