import GLib from 'gi://GLib';

let EXTENSION_PATH = null;

try {
	const [path] = GLib.filename_from_uri(import.meta.url);

	EXTENSION_PATH = GLib.path_get_dirname(path);
} catch (error) {
	EXTENSION_PATH = null;
};

function assetPath(name) {
	return EXTENSION_PATH ? GLib.build_filenamev([EXTENSION_PATH, 'assets', String(name ?? '')]) : null;
};

/**
 * Шлях до іконки налаштувань (`icons/settings/<name>.svg`).
 *
 * Потрібний у shell, де GTK не шукає в темі: іконки dw-* мають два
 * кольорові варіанти (-light/-dark) і не мають суфікса -symbolic, тож
 * їх не можна віддати через icon_name — тільки шляхом на диск.
 */
function settingsIconPath(name) {
	return EXTENSION_PATH
		? GLib.build_filenamev([EXTENSION_PATH, 'icons', 'settings', `${String(name ?? '')}.svg`])
		: null;
};

/**
 * Шлях до внутрішніх ресурсів віджета (`icons/widgets_settings/<widgetType>/<name>`).
 * Використовується для іконок керування, gif-анімацій тощо.
 */
function widgetResourcePath(widgetType, name) {
	return EXTENSION_PATH
		? GLib.build_filenamev([EXTENSION_PATH, 'icons', 'widgets_settings', String(widgetType ?? ''), String(name ?? '')])
		: null;
};


export { EXTENSION_PATH, assetPath, settingsIconPath, widgetResourcePath };
