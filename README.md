# Hermes Skills & Plugins Backup

Respaldo portable de **skills** y **plugins** de Hermes Agent.  
Listo para copiar a otro PC.

## Contenido

```
hermes-skills/
├── README.md              # Este archivo
├── INSTALL.md             # Guía de instalación
├── (skills en la raíz)    # 77 skills (121 MB)
├── plugins/               # 6 plugins (14 MB)
│   ├── hermes-relay/      # Gateway relay para canales de chat
│   ├── holographic/       # Diagramas SVG arquitectónicos
│   ├── homeassistant/     # Integración con Home Assistant
│   ├── honcho/            # Cloudflare Honcho
│   ├── quota/             # Límites y cuotas
│   └── spotify/           # Integración con Spotify
```

**Total:** 77 skills + 6 plugins = ~135 MB

## Instalación

### Requisitos
- Hermes Agent instalado
- Git (para clonar desde GitHub)

### Opción A: Clonar desde GitHub
```bash
git clone https://github.com/cjml555/hermes-skills.git ~/.hermes/skills-temp
cp -r ~/.hermes/skills-temp/* ~/.hermes/skills/
cp -r ~/.hermes/skills-temp/plugins/* ~/.hermes/plugins/
rm -rf ~/.hermes/skills-temp
```

### Opción B: Copiar carpeta completa (sin Git)
```bash
# Desde USB, red, o cualquier medio de transferencia
cp -r /ruta/origen/hermes-skills/* ~/.hermes/skills/
cp -r /ruta/origen/hermes-skills/plugins/* ~/.hermes/plugins/
```

### Opción C: Instalar skills individuales
```bash
# Solo skills específicos
cp -r /ruta/origen/hermes-skills/android-kotlin ~/.hermes/skills/
cp -r /ruta/origen/hermes-skills/xbox360-ppc-recomp-android ~/.hermes/skills/
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
