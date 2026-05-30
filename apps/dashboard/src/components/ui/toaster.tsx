import * as ToastPrimitive from "@radix-ui/react-toast";
import { cn } from "@/lib/utils";
import { useToast } from "./use-toast";

const toastVariants: Record<string, string> = {
  default: "border bg-background text-foreground",
  success: "border-success bg-success text-success-foreground",
  danger: "border-destructive bg-destructive text-destructive-foreground",
  warning: "border-warning bg-warning text-warning-foreground",
};

export function Toaster() {
  const { toasts } = useToast();

  return (
    <ToastPrimitive.Provider>
      <div className="fixed bottom-4 right-4 z-[100] flex flex-col-reverse gap-2">
        {toasts.map((t) => (
          <ToastPrimitive.Root
            key={t.id}
            open={true}
            onOpenChange={(open) => {
              if (!open) {
                // Toast will auto-dismiss
              }
            }}
            className={cn(
              "flex max-w-sm items-center justify-between space-x-4 rounded-lg border p-4 shadow-lg transition-all",
              toastVariants[t.variant ?? "default"]
            )}
          >
            <div className="flex-1">
              {t.title && (
                <ToastPrimitive.Title className="text-sm font-semibold">
                  {t.title}
                </ToastPrimitive.Title>
              )}
              {t.description && (
                <ToastPrimitive.Description className="text-sm opacity-90">
                  {t.description}
                </ToastPrimitive.Description>
              )}
            </div>
          </ToastPrimitive.Root>
        ))}
      </div>
      <ToastPrimitive.Viewport />
    </ToastPrimitive.Provider>
  );
}
