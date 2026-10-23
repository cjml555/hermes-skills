# Hermes Skills & Plugins Backup

Respaldo portable de **142 skills** (77 categorías) y **6 plugins** de Hermes Agent.
Listo para copiar a otro PC.

## Contenido

```
hermes-skills/
├── skills/          # 77 skills (121 MB)
│   ├── xbox360-ppc-recomp-android/
│   ├── android-kotlin/
│   ├── cloudflare/
│   ├── ...
│   └── (77 skills en total)
├── plugins/         # 6 plugins (14 MB)
│   ├── hermes-relay/       # Gateway relay para canales de chat
│   ├── holographic/        # Diagramas SVG arquitectónicos
│   ├── homeassistant/      # Integración con Home Assistant
│   ├── honcho/             # Cloudflare Honcho
│   ├── quota/              # Límites y cuotas
│   └── spotify/            # Integración con Spotify
├── README.md
└── INSTALL.md
```

## Instalación

### Requisitos
- Hermes Agent instalado
- Git (para clonar desde GitHub)

### Opción A: Clonar desde GitHub
```bash
git clone https://github.com/cjml555/hermes-skills.git ~/.hermes/skills-temp
cp -r ~/.hermes/skills-temp/skills/* ~/.hermes/skills/
cp -r ~/.hermes/skills-temp/plugins/* ~/.hermes/plugins/
rm -rf ~/.hermes/skills-temp
```

### Opción B: Copiar carpeta completa (sin Git)
```bash
# Desde USB, red, o cualquier medio de transferencia
cp -r /ruta/origen/hermes-skills/skills/* ~/.hermes/skills/
cp -r /ruta/origen/hermes-skills/plugins/* ~/.hermes/plugins/
```

### Opción C: Instalar skills individuales
```bash
# Solo skills específicos
cp -r /ruta/origen/hermes-skills/skills/xbox360-ppc-recomp-android ~/.hermes/skills/
cp -r /ruta/origen/hermes-skills/skills/android-kotlin ~/.hermes/skills/
```

## Verificación

```bash
# Contar skills instalados
ls ~/.hermes/skills/ | wc -l

# Ver plugins instalados
ls ~/.hermes/plugins/

# Verificar que Hermes los carga
# (reinicia Hermes y revisa la lista de skills disponibles)
```

## Notas

- **Licencia:** Cada skill/plugin mantiene su licencia original.
- **Tamaño total:** ~135 MB (skills + plugins).
- **Actualización:** Este backup es del 2026-10-23. Para actualizar, repite el proceso de exportación.
- **Privacidad:** Skills personalizados pueden contener datos sensibles. Revisa antes de subir a un repo público.

## Autor

Exportado por Hermes Agent (Jonathan, cjml555).
