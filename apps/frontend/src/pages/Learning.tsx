import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { Button, PageHeader } from "@/components/shared";
import { NeuralModelPanel } from "@/features/simulation/NeuralModelPanel";

export default function Learning() {
  return (
    <>
      <PageHeader
        title="Strojové učení"
        description="Neuronová síť se automaticky učí z vlastních jízd v simulaci."
      >
        <Button asChild variant="outline">
          <Link to="/warehouses">
            Generátor skladů
            <ArrowRight data-icon="inline-end" />
          </Link>
        </Button>
      </PageHeader>
      <NeuralModelPanel />
    </>
  );
}
