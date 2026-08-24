import { ExtensionContext } from "@foxglove/extension";

import { initAtlasDrivePanel } from "./AtlasDrivePanel";

export function activate(extensionContext: ExtensionContext): void {
  extensionContext.registerPanel({
    name: "ATLAS Smooth Drive",
    initPanel: initAtlasDrivePanel,
  });
}
