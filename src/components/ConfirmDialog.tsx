import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

interface ConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description: string;
}

const ConfirmDialog = ({ open, onClose, onConfirm, title, description }: ConfirmDialogProps) => {
  return (
    <AlertDialog open={open} onOpenChange={(v) => !v && onClose()}>
      <AlertDialogContent className="max-w-md rounded-2xl bg-card p-8 text-center">
        <AlertDialogHeader>
          <AlertDialogTitle className="text-2xl font-bold text-foreground">{title}</AlertDialogTitle>
          <AlertDialogDescription className="text-muted-foreground">{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <div className="mt-6 flex gap-4 justify-center">
          <button
            onClick={onClose}
            className="rounded-full border-2 border-border px-8 py-3 text-sm font-bold uppercase tracking-wider text-muted-foreground transition-all hover:bg-muted"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="rounded-full bg-destructive px-8 py-3 text-sm font-bold uppercase tracking-wider text-destructive-foreground transition-all hover:opacity-90"
          >
            Yes, Proceed
          </button>
        </div>
      </AlertDialogContent>
    </AlertDialog>
  );
};

export default ConfirmDialog;
