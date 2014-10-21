#include <glib.h>

/* BpG-skip */
#define BD_SWAP_ERROR bd_swap_error_quark ()
typedef enum {
    BD_SWAP_ERROR_UNKNOWN_STATE,
    BD_SWAP_ERROR_ACTIVATE,
} BDSwapError;
/* BpG-skip-end */

/**
 * bd_swap_mkswap:
 * @device: a device to create swap space on
 * @label: (allow-none): a label for the swap space device
 * @error: (out): place to store error (if any)
 *
 * Returns: whether the swap space was successfully created or not
 */
gboolean bd_swap_mkswap (gchar *device, gchar *label, GError **error);

/**
 * bd_swap_swapon:
 * @device: swap device to activate
 * @priority: priority of the activated device or -1 to use the default
 * @error: (out): place to store error (if any)
 *
 * Returns: whether the swap device was successfully activated or not
 */
gboolean bd_swap_swapon (gchar *device, gint priority, GError **error);

/**
 * bd_swap_swapoff:
 * @device: swap device to deactivate
 * @error: (out): place to store error (if any)
 *
 * Returns: whether the swap device was successfully deactivated or not
 */
gboolean bd_swap_swapoff (gchar *device, GError **error);

/**
 * bd_swap_swapstatus:
 * @device: swap device to get status of
 * @error: (out): place to store error (if any)
 *
 * Returns: %TRUE if the swap device is active, %FALSE if not active or failed
 * to determine (@error) is set not a non-NULL value in such case)
 */
gboolean bd_swap_swapstatus (gchar *device, GError **error);
