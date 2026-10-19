import { api, ContentDetailItem } from "@/lib/api";
import { notFound } from "next/navigation";
import { AnalysisView } from "./AnalysisView";

interface Props {
  params: Promise<{ id: string }>;
}

export default async function AnalysisPage({ params }: Props) {
  const { id } = await params;
  let item: ContentDetailItem;
  try {
    item = await api.content.get(id);
  } catch {
    notFound();
  }

  return <AnalysisView item={item} />;
}
