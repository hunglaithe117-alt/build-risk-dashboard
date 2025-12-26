"use client"

import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"
import { X } from "lucide-react"

const SheetContext = React.createContext<{
    onOpenChange: (open: boolean) => void;
} | null>(null);

interface SheetProps {
    open?: boolean;
    onOpenChange?: (open: boolean) => void;
    children: React.ReactNode;
}

const Sheet = ({ open: controlledOpen, onOpenChange: controlledOnOpenChange, children }: SheetProps) => {
    const [internalOpen, setInternalOpen] = React.useState(false);

    const open = controlledOpen ?? internalOpen;
    const onOpenChange = controlledOnOpenChange ?? setInternalOpen;

    // Separate trigger from content
    const triggerChild = React.Children.toArray(children).find(
        (child) => React.isValidElement(child) && child.type === SheetTrigger
    );

    const contentChildren = React.Children.toArray(children).filter(
        (child) => !(React.isValidElement(child) && child.type === SheetTrigger)
    );

    return (
        <SheetContext.Provider value={{ onOpenChange }}>
            {triggerChild}

            {open && (
                <div className="fixed inset-0 z-50">
                    <div
                        className="fixed inset-0 bg-black/50 backdrop-blur-sm"
                        onClick={() => onOpenChange(false)}
                    />
                    {contentChildren}
                </div>
            )}
        </SheetContext.Provider>
    );
};

interface SheetTriggerProps {
    children: React.ReactNode;
    asChild?: boolean;
}

const SheetTrigger = ({ children, asChild }: SheetTriggerProps) => {
    const context = React.useContext(SheetContext);

    if (!context) {
        throw new Error("SheetTrigger must be used within a Sheet");
    }

    const handleClick = () => {
        context.onOpenChange(true);
    };

    if (asChild && React.isValidElement(children)) {
        return React.cloneElement(children as React.ReactElement<any>, {
            onClick: handleClick,
        });
    }

    return <button onClick={handleClick}>{children}</button>;
};

const sheetVariants = cva(
    "fixed z-50 h-full bg-background p-6 shadow-lg border-l animate-in",
    {
        variants: {
            side: {
                left: "left-0 top-0 slide-in-from-left",
                right: "right-0 top-0 slide-in-from-right",
            },
            size: {
                default: "w-80",
                sm: "w-72",
                lg: "w-[480px]",
                xl: "w-[640px]",
                "2xl": "w-[800px]",
                full: "w-screen",
            },
        },
        defaultVariants: {
            side: "right",
            size: "default",
        },
    }
);

interface SheetContentProps
    extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof sheetVariants> {
    showClose?: boolean;
}

const SheetContent = React.forwardRef<HTMLDivElement, SheetContentProps>(
    ({ className, children, side = "right", size = "default", showClose = true, ...props }, ref) => {
        const context = React.useContext(SheetContext);

        return (
            <div
                ref={ref}
                className={cn(sheetVariants({ side, size }), className)}
                {...props}
            >
                {showClose && (
                    <button
                        className="absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                        onClick={() => context?.onOpenChange(false)}
                    >
                        <X className="h-4 w-4" />
                        <span className="sr-only">Close</span>
                    </button>
                )}
                {children}
            </div>
        );
    }
);
SheetContent.displayName = "SheetContent";

const SheetHeader = ({
    className,
    ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
    <div
        className={cn(
            "flex flex-col space-y-2 text-left",
            className
        )}
        {...props}
    />
);
SheetHeader.displayName = "SheetHeader";

const SheetTitle = React.forwardRef<
    HTMLParagraphElement,
    React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
    <h3
        ref={ref}
        className={cn(
            "text-lg font-semibold leading-none tracking-tight",
            className
        )}
        {...props}
    />
));
SheetTitle.displayName = "SheetTitle";

const SheetDescription = React.forwardRef<
    HTMLParagraphElement,
    React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
    <p
        ref={ref}
        className={cn("text-sm text-muted-foreground", className)}
        {...props}
    />
));
SheetDescription.displayName = "SheetDescription";

const SheetFooter = ({
    className,
    ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
    <div
        className={cn(
            "flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2",
            className
        )}
        {...props}
    />
);
SheetFooter.displayName = "SheetFooter";

const SheetClose = React.forwardRef<
    HTMLButtonElement,
    React.ButtonHTMLAttributes<HTMLButtonElement>
>(({ className, ...props }, ref) => {
    const context = React.useContext(SheetContext);

    return (
        <button
            ref={ref}
            className={className}
            onClick={() => context?.onOpenChange(false)}
            {...props}
        />
    );
});
SheetClose.displayName = "SheetClose";

export {
    Sheet,
    SheetClose,
    SheetContent,
    SheetDescription,
    SheetFooter,
    SheetHeader,
    SheetTitle,
    SheetTrigger,
};
